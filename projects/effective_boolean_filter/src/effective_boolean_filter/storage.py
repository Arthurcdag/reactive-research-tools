"""Report storage backends.

The API stores `EvaluationReport` JSON dicts keyed by report id. Three backends:

* :class:`InMemoryStore` - default, ephemeral, loses data on restart.
* :class:`FileStore`     - one ``<report_id>.json`` file under a directory.
* :class:`TenantReportStore` - rows in the SQLite tenant database. Supports
  per-tenant scoping and a retention window via ``expires_at``.

Selection at runtime via the ``EBF_REPORT_STORE`` env var:

* unset / ``memory``         - :class:`InMemoryStore`
* ``file:/path/to/dir``      - :class:`FileStore` rooted at the given path
* ``tenant:/path/to/db``     - :class:`TenantReportStore` against a shared
                               SQLite tenant database. The same path may
                               also be referenced by ``EBF_TENANT_DB``;
                               specifying both is allowed and makes the
                               auth and report paths share one database.

Storage instances are safe for use across requests within one process. The
file backend uses an atomic ``os.replace`` write so concurrent writers do
not produce half-written files; the tenant backend serialises through
SQLite. For cross-process locking, the tenant backend is the right pick.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator, Protocol


_VALID_ID = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def _check_id(report_id: str) -> None:
    """Reject ids that could escape the storage directory."""
    if not _VALID_ID.match(report_id):
        raise ValueError(f"invalid report id: {report_id!r}")


class ReportStore(Protocol):
    def put(self, report_id: str, report: dict[str, Any]) -> None: ...
    def get(self, report_id: str) -> dict[str, Any] | None: ...
    def list_ids(self) -> list[str]: ...
    def __contains__(self, report_id: str) -> bool: ...


class InMemoryStore:
    """Process-local dict, lost on restart."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, report_id: str, report: dict[str, Any]) -> None:
        _check_id(report_id)
        with self._lock:
            self._data[report_id] = report

    def get(self, report_id: str) -> dict[str, Any] | None:
        _check_id(report_id)
        with self._lock:
            return self._data.get(report_id)

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._data)

    def __contains__(self, report_id: str) -> bool:
        try:
            _check_id(report_id)
        except ValueError:
            return False
        with self._lock:
            return report_id in self._data


class FileStore:
    """One JSON file per report under ``root``.

    Atomic writes via tempfile + ``os.replace``. No global lock: each report
    id has its own file.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, report_id: str) -> Path:
        _check_id(report_id)
        return self.root / f"{report_id}.json"

    def put(self, report_id: str, report: dict[str, Any]) -> None:
        path = self._path(report_id)
        # write to a sibling tempfile then atomically replace
        fd, tmp = tempfile.mkstemp(prefix=f".{report_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            # tempfile cleanup best-effort
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def get(self, report_id: str) -> dict[str, Any] | None:
        path = self._path(report_id)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        ids: list[str] = []
        for p in self.root.iterdir():
            if p.suffix != ".json" or p.name.startswith("."):
                continue
            stem = p.stem
            if _VALID_ID.match(stem):
                ids.append(stem)
        return sorted(ids)

    def __contains__(self, report_id: str) -> bool:
        try:
            return self._path(report_id).exists()
        except ValueError:
            return False


class TenantReportStore:
    """Report storage backed by the SQLite tenant database.

    Wraps a :class:`tenant_db.TenantDatabase`. The store itself is
    tenant-agnostic at the ``ReportStore`` protocol boundary (the API
    middleware passes a per-request tenant when it has one), so the
    contract stays compatible with the older two backends.

    ``default_tenant_id`` is attached to writes that arrive without an
    explicit tenant — useful for tests and for the local-demo flow
    where every report goes to the same tenant slug.
    """

    def __init__(
        self,
        db: "tenant_db.TenantDatabase",
        *,
        default_tenant_id: str | None = None,
    ) -> None:
        # imported lazily inside __init__ to avoid a top-level cycle
        # with tenant_db (which doesn't import storage).
        self._db = db
        self._default_tenant_id = default_tenant_id

    def put(
        self,
        report_id: str,
        report: dict[str, Any],
        *,
        tenant_id: str | None = None,
        expires_at: str | None = None,
    ) -> None:
        _check_id(report_id)
        self._db.put_report(
            report_id,
            report,
            tenant_id=tenant_id or self._default_tenant_id,
            expires_at=expires_at,
        )

    def get(self, report_id: str) -> dict[str, Any] | None:
        _check_id(report_id)
        return self._db.get_report(report_id)

    def list_ids(self) -> list[str]:
        return sorted(self._db.list_report_ids())

    def __contains__(self, report_id: str) -> bool:
        try:
            _check_id(report_id)
        except ValueError:
            return False
        return self._db.get_report(report_id) is not None


def get_store(spec: str | None = None) -> ReportStore:
    """Resolve a store from a spec string.

    ``None`` / ``""`` / ``"memory"``  -> :class:`InMemoryStore`
    ``"file:/some/dir"``              -> :class:`FileStore`
    ``"tenant:/some/db.sqlite"``      -> :class:`TenantReportStore`

    Falls back to the ``EBF_REPORT_STORE`` env var when ``spec`` is None.
    """
    if spec is None:
        spec = os.environ.get("EBF_REPORT_STORE", "")
    spec = spec.strip()
    if not spec or spec == "memory":
        return InMemoryStore()
    if spec.startswith("file:"):
        path = spec[len("file:"):]
        if not path:
            raise ValueError("file: store spec requires a path: 'file:/path/to/dir'")
        return FileStore(path)
    if spec.startswith("tenant:"):
        path = spec[len("tenant:"):]
        if not path:
            raise ValueError(
                "tenant: store spec requires a SQLite path: "
                "'tenant:/path/to/db.sqlite'"
            )
        # Imported here so the storage module stays usable when the
        # tenant_db extras are not needed.
        from . import tenant_db

        return TenantReportStore(tenant_db.TenantDatabase(path))
    raise ValueError(f"unknown report store spec: {spec!r}")


def iter_all(store: ReportStore) -> Iterator[dict[str, Any]]:
    for rid in store.list_ids():
        rep = store.get(rid)
        if rep is not None:
            yield rep
