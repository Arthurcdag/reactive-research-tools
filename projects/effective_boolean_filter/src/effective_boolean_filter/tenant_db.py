"""SQLite-backed tenant database for API keys and report retention.

This is the per-tenant backend the project board has been planning for: it
replaces the ``EBF_API_KEYS`` env-var list (env keys keep working as a
fast back-compat path) and the file ``ReportStore`` (also kept; the DB
is selected explicitly via ``EBF_REPORT_STORE=tenant:/path/to/db.sqlite``).

Design choices, all of them load-bearing:

* **SQLite, stdlib only.** No new dependency, no daemon to run, lives in
  the same Docker volume as the file report store. Easy to migrate to
  Postgres later — the SQL is plain ANSI.

* **Two fingerprints per API key.** ``token_lookup_hash`` is SHA-256 of
  the plaintext token; it is the unique key the auth path uses for O(1)
  lookup on every request. ``token_display_fingerprint`` is the
  existing PBKDF2 fingerprint that already appears in
  ``customer_registry.json`` and operator reconciliation reports — we
  keep producing it so the two systems agree about which key is which.
  Per-request PBKDF2 would be ~10 ms; that's fine for the env-var path
  (hashed once at startup) but wrong for the DB path (hashed every
  request). SHA-256 of a high-entropy ``secrets.token_urlsafe(32)``
  token is the standard production choice and what Stripe / AWS do.

* **Plaintext tokens are never stored.** ``provision_api_key`` returns
  the plaintext once and the caller is responsible for handing it to
  the customer (or to ``EBF_API_KEYS``). The DB only sees hashes.

* **Migrations are tracked.** Every schema change bumps
  ``CURRENT_SCHEMA_VERSION`` and adds an entry to ``_MIGRATIONS``.
  Re-opening a DB at the current version is a no-op; re-opening an
  older DB runs the missing migrations in order. The ``schema_migrations``
  table records what has been applied, so the process is idempotent.

* **Tenant id == customer id.** Throughout this codebase the existing
  vocabulary is ``customer_id`` (the registry slug). The DB column is
  ``tenant_id`` for namespace clarity, but the two are the same string
  by convention. CLI and webhook callers pass the slug in either name
  and the DB stores it under ``tenant_id``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


# ---------------------------------------------------------------------------
# schema versioning
# ---------------------------------------------------------------------------


CURRENT_SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id TEXT PRIMARY KEY,
            plan TEXT NOT NULL,
            status TEXT NOT NULL,
            payment_reference TEXT NOT NULL DEFAULT '',
            contracting_entity TEXT NOT NULL DEFAULT '',
            monthly_amount TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            token_lookup_hash TEXT NOT NULL UNIQUE,
            token_display_fingerprint TEXT NOT NULL,
            plan TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT,
            revoked_at TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);

        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_tenant ON reports(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_reports_expires ON reports(expires_at);
    """,
}


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------


VALID_PLANS: frozenset[str] = frozenset({"demo", "starter", "pro", "enterprise"})
VALID_TENANT_STATUSES: frozenset[str] = frozenset({"active", "suspended", "canceled"})
VALID_KEY_STATUSES: frozenset[str] = frozenset({"active", "revoked"})

# Slug rules mirror scripts/provision_customer_key.py so a slug minted on
# either side is accepted by the other.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$")
_KEY_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
_REPORT_ID_RE = re.compile(r"^[A-Za-z0-9_:.-]{1,128}$")

# Same salt/rounds as operations._fingerprint so the display fingerprint
# in the DB matches the one in customer_registry.json byte-for-byte.
_FINGERPRINT_SALT = b"effective-boolean-filter-api-key-fingerprint-v1"
_FINGERPRINT_ROUNDS = 120_000

# SHA-256 input prefix for the DB lookup hash. Domain-separates the
# lookup hash from any other use of SHA-256(token) in the codebase.
_LOOKUP_HASH_NAMESPACE = b"ebf-tenant-db-api-key-lookup-v1\x00"


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------


class TenantDBError(Exception):
    """Base for tenant-database failures."""


class TenantNotFoundError(TenantDBError):
    pass


class ApiKeyNotFoundError(TenantDBError):
    pass


class DuplicateTenantError(TenantDBError):
    pass


class ValidationError(TenantDBError):
    pass


# ---------------------------------------------------------------------------
# row types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenantRow:
    tenant_id: str
    plan: str
    status: str
    payment_reference: str
    contracting_entity: str
    monthly_amount: str
    currency: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "plan": self.plan,
            "status": self.status,
            "payment_reference": self.payment_reference,
            "contracting_entity": self.contracting_entity,
            "monthly_amount": self.monthly_amount,
            "currency": self.currency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ApiKeyRow:
    key_id: str
    tenant_id: str
    token_display_fingerprint: str
    plan: str
    status: str
    created_at: str
    last_seen_at: str | None
    revoked_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "tenant_id": self.tenant_id,
            "token_display_fingerprint": self.token_display_fingerprint,
            "plan": self.plan,
            "status": self.status,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
            "revoked_at": self.revoked_at,
        }


@dataclass(frozen=True)
class ProvisionedApiKey:
    """Return value from :meth:`TenantDatabase.provision_api_key`.

    ``token`` is the plaintext shown once; the DB never sees it again.
    """

    key_id: str
    tenant_id: str
    plan: str
    token: str
    token_display_fingerprint: str
    created_at: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_slug(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    candidate = value.strip().lower()
    if not _SLUG_RE.match(candidate):
        raise ValidationError(
            f"{label} must be 3-64 chars: lowercase letters, numbers, '-' or '_'"
        )
    return candidate


def _require_key_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("key_id must be a string")
    candidate = value.strip().lower()
    if not _KEY_ID_RE.match(candidate):
        raise ValidationError(
            "key_id must be 1-64 chars: lowercase letters, numbers, '-' or '_'"
        )
    return candidate


def _require_plan(value: str) -> str:
    if value not in VALID_PLANS:
        raise ValidationError(
            f"plan must be one of {sorted(VALID_PLANS)}; got {value!r}"
        )
    return value


def _require_tenant_status(value: str) -> str:
    if value not in VALID_TENANT_STATUSES:
        raise ValidationError(
            f"tenant status must be one of {sorted(VALID_TENANT_STATUSES)}; "
            f"got {value!r}"
        )
    return value


def _require_report_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("report_id must be a string")
    if not _REPORT_ID_RE.match(value):
        raise ValidationError("report_id contains disallowed characters")
    return value


def token_lookup_hash(token: str) -> str:
    """Fast lookup hash for ``token`` (SHA-256 with a namespace prefix).

    This is the value stored in ``api_keys.token_lookup_hash`` and
    queried at auth time. SHA-256 is fast (~1 µs) and safe here because
    the underlying tokens are 256-bit random
    (``secrets.token_urlsafe(32)``), so a single un-iterated hash gives
    full preimage resistance against any practical attack.
    """
    if not isinstance(token, str) or not token:
        raise ValidationError("token must be a non-empty string")
    return hashlib.sha256(_LOOKUP_HASH_NAMESPACE + token.encode("utf-8")).hexdigest()


def token_display_fingerprint(token: str) -> str:
    """PBKDF2 fingerprint matching ``customer_registry.json`` byte-for-byte.

    Same salt and rounds as ``operations._fingerprint`` / the registry
    field already produced by ``scripts/provision_customer_key.py``; the
    8-byte digest hex is what shows up in reconciliation reports.
    """
    if not isinstance(token, str) or not token:
        raise ValidationError("token must be a non-empty string")
    return hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        _FINGERPRINT_SALT,
        _FINGERPRINT_ROUNDS,
        dklen=8,
    ).hex()


# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------


class TenantDatabase:
    """SQLite tenant database.

    Open one of these per process. The class is safe to use across
    threads because every method opens a short-lived connection through
    :meth:`_connect`; SQLite handles the concurrency. For tests, pass
    ``":memory:"`` as the path.
    """

    def __init__(self, path: str | Path) -> None:
        if isinstance(path, Path):
            self.path: str = str(path)
        else:
            self.path = path
        if self.path != ":memory:":
            parent = Path(self.path).parent
            if str(parent):
                parent.mkdir(parents=True, exist_ok=True)
        # Connection used only for in-memory mode; on disk we open fresh
        # connections per call so the file is durable across method
        # boundaries.
        self._memory_conn: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
            self._configure(self._memory_conn)
        with self._connect() as conn:
            self._migrate(conn)

    # ----- connection management -----

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return _NonClosingConnection(self._memory_conn)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        self._configure(conn)
        return conn

    @staticmethod
    def _configure(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL is friendlier for concurrent reads; harmless in tests.
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            # WAL needs file-backed storage; in :memory: it's a no-op.
            pass

    # ----- migrations -----

    def _migrate(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied: set[int] = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
            for version in sorted(_MIGRATIONS):
                if version in applied:
                    continue
                conn.executescript(_MIGRATIONS[version])
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (version, _now_iso()),
                )

    def schema_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS v FROM schema_migrations"
            ).fetchone()
            return int(row["v"] or 0)

    # ----- tenants -----

    def upsert_tenant(
        self,
        tenant_id: str,
        *,
        plan: str,
        status: str = "active",
        payment_reference: str = "",
        contracting_entity: str = "",
        monthly_amount: str = "",
        currency: str = "",
    ) -> TenantRow:
        tid = _require_slug(tenant_id, "tenant_id")
        plan = _require_plan(plan)
        status = _require_tenant_status(status)
        now = _now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM tenants WHERE tenant_id = ?", (tid,)
            ).fetchone()
            if existing is None:
                with conn:
                    conn.execute(
                        "INSERT INTO tenants("
                        "tenant_id, plan, status, payment_reference, "
                        "contracting_entity, monthly_amount, currency, "
                        "created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            tid,
                            plan,
                            status,
                            payment_reference.strip(),
                            contracting_entity.strip(),
                            monthly_amount.strip(),
                            (currency or "").strip().upper(),
                            now,
                            now,
                        ),
                    )
            else:
                with conn:
                    conn.execute(
                        "UPDATE tenants SET "
                        "plan = ?, status = ?, payment_reference = ?, "
                        "contracting_entity = ?, monthly_amount = ?, "
                        "currency = ?, updated_at = ? "
                        "WHERE tenant_id = ?",
                        (
                            plan,
                            status,
                            payment_reference.strip(),
                            contracting_entity.strip(),
                            monthly_amount.strip(),
                            (currency or "").strip().upper(),
                            now,
                            tid,
                        ),
                    )
            return self.get_tenant(tid)

    def get_tenant(self, tenant_id: str) -> TenantRow:
        tid = _require_slug(tenant_id, "tenant_id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tenants WHERE tenant_id = ?", (tid,)
            ).fetchone()
            if row is None:
                raise TenantNotFoundError(f"tenant_id {tid!r} not found")
            return _row_to_tenant(row)

    def find_tenant(self, tenant_id: str) -> TenantRow | None:
        try:
            return self.get_tenant(tenant_id)
        except TenantNotFoundError:
            return None

    def list_tenants(self) -> list[TenantRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tenants ORDER BY tenant_id"
            ).fetchall()
            return [_row_to_tenant(row) for row in rows]

    def set_tenant_status(self, tenant_id: str, status: str) -> TenantRow:
        tid = _require_slug(tenant_id, "tenant_id")
        status = _require_tenant_status(status)
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    "UPDATE tenants SET status = ?, updated_at = ? "
                    "WHERE tenant_id = ?",
                    (status, _now_iso(), tid),
                )
            if cur.rowcount == 0:
                raise TenantNotFoundError(f"tenant_id {tid!r} not found")
        return self.get_tenant(tid)

    def set_tenant_plan(self, tenant_id: str, plan: str) -> TenantRow:
        tid = _require_slug(tenant_id, "tenant_id")
        plan = _require_plan(plan)
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    "UPDATE tenants SET plan = ?, updated_at = ? "
                    "WHERE tenant_id = ?",
                    (plan, _now_iso(), tid),
                )
                if cur.rowcount == 0:
                    raise TenantNotFoundError(f"tenant_id {tid!r} not found")
                # Keep active API key plan denormalisation in sync — a
                # plan change at the tenant level should also flow to its
                # currently-active keys so the auth path returns the
                # correct plan for rate limiting.
                conn.execute(
                    "UPDATE api_keys SET plan = ? "
                    "WHERE tenant_id = ? AND status = 'active'",
                    (plan, tid),
                )
        return self.get_tenant(tid)

    # ----- api keys -----

    def provision_api_key(
        self,
        *,
        tenant_id: str,
        key_id: str | None = None,
        plan: str | None = None,
        token_bytes: int = 32,
    ) -> ProvisionedApiKey:
        """Mint a new API key for ``tenant_id`` and return the plaintext once.

        ``plan`` defaults to the tenant's current plan. ``key_id`` is the
        short, customer-facing identifier (slug-form); if omitted, one is
        derived from the token fingerprint so it is stable but opaque.
        """
        tid = _require_slug(tenant_id, "tenant_id")
        if token_bytes < 24:
            raise ValidationError("token_bytes must be at least 24")
        tenant = self.get_tenant(tid)  # raises TenantNotFoundError
        plan_value = _require_plan(plan if plan is not None else tenant.plan)

        token = secrets.token_urlsafe(token_bytes)
        display_fp = token_display_fingerprint(token)
        lookup_hash = token_lookup_hash(token)

        if key_id is None:
            key_id_value = f"{tid}-{display_fp[:8]}"
        else:
            key_id_value = _require_key_id(key_id)

        now = _now_iso()
        with self._connect() as conn:
            with conn:
                conn.execute(
                    "INSERT INTO api_keys("
                    "key_id, tenant_id, token_lookup_hash, "
                    "token_display_fingerprint, plan, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        key_id_value,
                        tid,
                        lookup_hash,
                        display_fp,
                        plan_value,
                        "active",
                        now,
                    ),
                )
        return ProvisionedApiKey(
            key_id=key_id_value,
            tenant_id=tid,
            plan=plan_value,
            token=token,
            token_display_fingerprint=display_fp,
            created_at=now,
        )

    def find_active_key_by_token(self, token: str) -> ApiKeyRow | None:
        """O(1) lookup used by the auth path.

        Returns ``None`` if no active key matches; never raises on
        misses (auth treats a miss as "no identity"). On a hit, the
        ``last_seen_at`` column is updated and the returned
        :class:`ApiKeyRow` reflects the new timestamp.
        """
        if not isinstance(token, str) or not token:
            return None
        try:
            lookup = token_lookup_hash(token)
        except ValidationError:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys "
                "WHERE token_lookup_hash = ? AND status = 'active'",
                (lookup,),
            ).fetchone()
            if row is None:
                return None
            now = _now_iso()
            with conn:
                conn.execute(
                    "UPDATE api_keys SET last_seen_at = ? WHERE key_id = ?",
                    (now, row["key_id"]),
                )
            # Return a row that reflects the just-applied UPDATE.
            base = _row_to_api_key(row)
            return ApiKeyRow(
                key_id=base.key_id,
                tenant_id=base.tenant_id,
                token_display_fingerprint=base.token_display_fingerprint,
                plan=base.plan,
                status=base.status,
                created_at=base.created_at,
                last_seen_at=now,
                revoked_at=base.revoked_at,
            )

    def get_api_key(self, key_id: str) -> ApiKeyRow:
        kid = _require_key_id(key_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key_id = ?", (kid,)
            ).fetchone()
            if row is None:
                raise ApiKeyNotFoundError(f"key_id {kid!r} not found")
            return _row_to_api_key(row)

    def list_api_keys(self, tenant_id: str | None = None) -> list[ApiKeyRow]:
        with self._connect() as conn:
            if tenant_id is None:
                rows = conn.execute(
                    "SELECT * FROM api_keys ORDER BY created_at"
                ).fetchall()
            else:
                tid = _require_slug(tenant_id, "tenant_id")
                rows = conn.execute(
                    "SELECT * FROM api_keys WHERE tenant_id = ? "
                    "ORDER BY created_at",
                    (tid,),
                ).fetchall()
            return [_row_to_api_key(row) for row in rows]

    def revoke_api_key(self, key_id: str) -> ApiKeyRow:
        kid = _require_key_id(key_id)
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    "UPDATE api_keys SET status = 'revoked', revoked_at = ? "
                    "WHERE key_id = ? AND status = 'active'",
                    (_now_iso(), kid),
                )
            if cur.rowcount == 0:
                # Was the key missing, or just already revoked?
                existing = conn.execute(
                    "SELECT * FROM api_keys WHERE key_id = ?", (kid,)
                ).fetchone()
                if existing is None:
                    raise ApiKeyNotFoundError(f"key_id {kid!r} not found")
        return self.get_api_key(kid)

    # ----- reports -----

    def put_report(
        self,
        report_id: str,
        payload: Mapping[str, Any],
        *,
        tenant_id: str | None = None,
        expires_at: str | None = None,
    ) -> None:
        rid = _require_report_id(report_id)
        if not isinstance(payload, Mapping):
            raise ValidationError("payload must be a dict-like mapping")
        tid = _require_slug(tenant_id, "tenant_id") if tenant_id else None
        with self._connect() as conn:
            with conn:
                conn.execute(
                    "INSERT INTO reports("
                    "report_id, tenant_id, payload, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(report_id) DO UPDATE SET "
                    "payload = excluded.payload, "
                    "tenant_id = excluded.tenant_id, "
                    "expires_at = excluded.expires_at",
                    (
                        rid,
                        tid,
                        json.dumps(dict(payload), sort_keys=True),
                        _now_iso(),
                        expires_at,
                    ),
                )

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        rid = _require_report_id(report_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, expires_at FROM reports WHERE report_id = ?",
                (rid,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"]:
                # Treat already-expired rows as deleted from the caller's
                # perspective; a reaper can sweep them later.
                if row["expires_at"] <= _now_iso():
                    return None
            return json.loads(row["payload"])

    def list_report_ids(self, tenant_id: str | None = None) -> list[str]:
        with self._connect() as conn:
            if tenant_id is None:
                rows = conn.execute(
                    "SELECT report_id FROM reports ORDER BY created_at"
                ).fetchall()
            else:
                tid = _require_slug(tenant_id, "tenant_id")
                rows = conn.execute(
                    "SELECT report_id FROM reports WHERE tenant_id = ? "
                    "ORDER BY created_at",
                    (tid,),
                ).fetchall()
            return [r["report_id"] for r in rows]

    def delete_expired_reports(self, *, now: str | None = None) -> int:
        """Reap reports whose ``expires_at`` is in the past.

        Returns the number of rows deleted. Operators run this on a
        schedule (cron, systemd timer, or a sidecar). It is also called
        by the CLI ``tenant-db reports reap``.
        """
        cutoff = now if now is not None else _now_iso()
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    "DELETE FROM reports "
                    "WHERE expires_at IS NOT NULL AND expires_at <= ?",
                    (cutoff,),
                )
            return cur.rowcount or 0


# ---------------------------------------------------------------------------
# row → dataclass mappers
# ---------------------------------------------------------------------------


def _row_to_tenant(row: sqlite3.Row) -> TenantRow:
    return TenantRow(
        tenant_id=row["tenant_id"],
        plan=row["plan"],
        status=row["status"],
        payment_reference=row["payment_reference"],
        contracting_entity=row["contracting_entity"],
        monthly_amount=row["monthly_amount"],
        currency=row["currency"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_api_key(row: sqlite3.Row) -> ApiKeyRow:
    return ApiKeyRow(
        key_id=row["key_id"],
        tenant_id=row["tenant_id"],
        token_display_fingerprint=row["token_display_fingerprint"],
        plan=row["plan"],
        status=row["status"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        revoked_at=row["revoked_at"],
    )


# ---------------------------------------------------------------------------
# connection wrappers
# ---------------------------------------------------------------------------


class _NonClosingConnection:
    """Context-manager wrapper that does NOT close the underlying connection.

    Used for the in-memory test mode so a single shared SQLite connection
    survives across method calls (closing it would lose the schema).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


# ---------------------------------------------------------------------------
# environment loader
# ---------------------------------------------------------------------------


def parse_tenant_db_dsn(value: str | None) -> str | None:
    """Parse ``EBF_TENANT_DB`` into a SQLite path.

    Accepted forms::

        tenant:/abs/path/to/db.sqlite
        sqlite:/abs/path/to/db.sqlite
        /abs/path/to/db.sqlite

    Returns ``None`` for unset/blank input — that disables the DB and
    callers fall back to env-var keys and file/memory report stores.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    for prefix in ("tenant:", "sqlite:"):
        if raw.startswith(prefix):
            return raw[len(prefix):]
    return raw


def open_tenant_db_from_env(
    env: Mapping[str, str] | None = None,
) -> TenantDatabase | None:
    """Open a tenant DB from ``EBF_TENANT_DB``, or return None when unset."""
    source = dict(os.environ if env is None else env)
    path = parse_tenant_db_dsn(source.get("EBF_TENANT_DB"))
    if path is None:
        return None
    return TenantDatabase(path)


# ---------------------------------------------------------------------------
# registry-to-DB sync
# ---------------------------------------------------------------------------


def sync_tenants_from_registry(
    db: TenantDatabase,
    registry_path: str | Path,
) -> dict[str, int]:
    """Upsert tenant rows from a ``rtt_customer_registry_v1`` JSON file.

    Returns counts of ``{"inserted": n, "updated": m, "skipped": k}``.
    Used by the admin CLI when migrating an existing operator setup
    into the DB, and as a backfill when the webhook's best-effort DB
    mirror has fallen behind.
    """
    path = Path(registry_path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != "rtt_customer_registry_v1":
        raise ValidationError(
            f"registry {path} has unsupported schema {data.get('schema')!r}"
        )
    customers = data.get("customers") or []
    if not isinstance(customers, list):
        raise ValidationError(f"registry {path} customers field is not a list")

    inserted = 0
    updated = 0
    skipped = 0
    for item in customers:
        if not isinstance(item, Mapping):
            skipped += 1
            continue
        tid_raw = item.get("customer_id")
        plan = item.get("plan")
        status = item.get("status")
        if (
            not isinstance(tid_raw, str)
            or not isinstance(plan, str)
            or not isinstance(status, str)
            or plan not in VALID_PLANS
            or status not in VALID_TENANT_STATUSES
        ):
            skipped += 1
            continue
        existed = db.find_tenant(tid_raw) is not None
        db.upsert_tenant(
            tid_raw,
            plan=plan,
            status=status,
            payment_reference=str(item.get("payment_reference", "")),
            contracting_entity=str(item.get("contracting_entity", "")),
            monthly_amount=str(item.get("monthly_amount", "")),
            currency=str(item.get("currency", "")),
        )
        if existed:
            updated += 1
        else:
            inserted += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "VALID_PLANS",
    "VALID_TENANT_STATUSES",
    "VALID_KEY_STATUSES",
    "TenantDBError",
    "TenantNotFoundError",
    "ApiKeyNotFoundError",
    "DuplicateTenantError",
    "ValidationError",
    "TenantRow",
    "ApiKeyRow",
    "ProvisionedApiKey",
    "TenantDatabase",
    "token_lookup_hash",
    "token_display_fingerprint",
    "parse_tenant_db_dsn",
    "open_tenant_db_from_env",
    "sync_tenants_from_registry",
]
# Silence the unused-imports linter on closing import kept for future use.
_ = closing, Iterable
