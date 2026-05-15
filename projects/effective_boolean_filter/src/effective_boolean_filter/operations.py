"""Operational controls for public/commercial deployments.

The default app remains local-demo friendly: no API key requirement and no
rate limit unless explicitly enabled. Public deployments opt in with env vars.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping


PUBLIC_PATHS = {
    "/health",
    "/commercial/plans",
    "/legal/terms",
    "/legal/privacy",
    # Payment webhook is signature-gated (the provider's secret is the
    # auth), so it must bypass the API-key check. Rate-limiting it would
    # also be wrong: Stripe retries on non-2xx and our own 429 would
    # cause delivery drops on real events.
    "/commercial/webhook/stripe",
}

DEFAULT_PLAN_LIMITS = {
    "anonymous": "20/minute",
    "demo": "30/minute",
    "starter": "120/minute",
    "pro": "600/minute",
    "enterprise": "1800/minute",
}
_FINGERPRINT_SALT = b"effective-boolean-filter-api-key-fingerprint-v1"
_FINGERPRINT_ROUNDS = 120_000


@dataclass(frozen=True)
class ConfiguredApiKey:
    key_id: str
    plan: str
    token: str
    fingerprint: str


@dataclass(frozen=True)
class AccessIdentity:
    key_id: str
    plan: str
    fingerprint: str


@dataclass(frozen=True)
class AuthResult:
    identity: AccessIdentity | None
    bootstrap_token: str | None = None


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int
    label: str


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_at: int
    retry_after: int

    def headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
        }
        if not self.allowed:
            headers["Retry-After"] = str(max(1, self.retry_after))
        return headers


@dataclass(frozen=True)
class AccessConfig:
    public_mode: bool
    require_api_key: bool
    api_keys: tuple[ConfiguredApiKey, ...]
    cookie_name: str
    cookie_secure: bool
    docs_enabled: bool
    rate_limit_enabled: bool
    plan_limits: Mapping[str, RateLimit]
    default_plan: str


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _fingerprint(token: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        _FINGERPRINT_SALT,
        _FINGERPRINT_ROUNDS,
        dklen=8,
    ).hex()


def parse_api_keys(value: str, *, default_plan: str = "starter") -> tuple[ConfiguredApiKey, ...]:
    """Parse comma-separated API key specs.

    Supported forms:
      token
      key_id:token
      key_id:plan:token
    """
    keys: list[ConfiguredApiKey] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(":", 2)]
        if len(parts) == 1:
            token = parts[0]
            key_id = f"key_{_fingerprint(token)[:8]}"
            plan = default_plan
        elif len(parts) == 2:
            key_id, token = parts
            plan = default_plan
        else:
            key_id, plan, token = parts
        if not key_id or not token:
            continue
        keys.append(
            ConfiguredApiKey(
                key_id=key_id,
                plan=plan or default_plan,
                token=token,
                fingerprint=_fingerprint(token),
            )
        )
    return tuple(keys)


_LIMIT_RE = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour|day)s?\s*$", re.I)


def parse_rate_limit(value: str) -> RateLimit:
    match = _LIMIT_RE.match(value)
    if not match:
        raise ValueError(f"invalid rate limit {value!r}; expected '120/minute'")
    limit = int(match.group(1))
    unit = match.group(2).lower()
    seconds = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }[unit]
    return RateLimit(limit=limit, window_seconds=seconds, label=f"{limit}/{unit}")


def _load_plan_limits(env: Mapping[str, str]) -> Mapping[str, RateLimit]:
    default_spec = env.get("EBF_RATE_LIMIT_DEFAULT", DEFAULT_PLAN_LIMITS["starter"])
    limits = {
        plan: parse_rate_limit(env.get(f"EBF_PLAN_{plan.upper()}_RATE_LIMIT", spec))
        for plan, spec in DEFAULT_PLAN_LIMITS.items()
    }
    limits["default"] = parse_rate_limit(default_spec)

    custom = env.get("EBF_PLAN_LIMITS", "")
    for raw_item in custom.split(","):
        item = raw_item.strip()
        if not item or "=" not in item:
            continue
        plan, spec = item.split("=", 1)
        limits[plan.strip()] = parse_rate_limit(spec.strip())
    return limits


def load_access_config(env: Mapping[str, str] | None = None) -> AccessConfig:
    source = dict(os.environ if env is None else env)
    public_mode = _truthy(source.get("EBF_PUBLIC_MODE"))
    default_plan = source.get("EBF_DEFAULT_PLAN", "starter").strip() or "starter"
    api_keys = parse_api_keys(source.get("EBF_API_KEYS", ""), default_plan=default_plan)
    require_api_key = public_mode or _truthy(source.get("EBF_REQUIRE_API_KEY"))
    docs_enabled = _truthy(source.get("EBF_ENABLE_DOCS")) or (
        not public_mode and not _truthy(source.get("EBF_DISABLE_DOCS"))
    )
    return AccessConfig(
        public_mode=public_mode,
        require_api_key=require_api_key,
        api_keys=api_keys,
        cookie_name=source.get("EBF_AUTH_COOKIE", "ebf_access_key"),
        cookie_secure=(
            _truthy(source.get("EBF_COOKIE_SECURE"))
            if "EBF_COOKIE_SECURE" in source
            else public_mode
        ),
        docs_enabled=docs_enabled,
        rate_limit_enabled=public_mode or _truthy(source.get("EBF_RATE_LIMIT_ENABLED")),
        plan_limits=_load_plan_limits(source),
        default_plan=default_plan,
    )


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS


def authenticate_request(
    request: Any,
    config: AccessConfig,
    *,
    tenant_db: Any | None = None,
) -> AuthResult:
    """Resolve the caller's :class:`AccessIdentity` from request credentials.

    Two key sources, checked in order:

    1. ``config.api_keys`` (loaded from ``EBF_API_KEYS``) — fast
       plaintext compare. This is the legacy path and stays the primary
       store until operators migrate everyone to the DB.

    2. ``tenant_db`` (when ``EBF_TENANT_DB`` is set) — SHA-256 lookup
       hash, O(1) per-request. The DB key's ``plan`` field drives rate
       limiting just like an env-var key would.

    Either path can succeed; a hit in the env list short-circuits the
    DB. A miss in both yields ``AuthResult(identity=None)`` and the
    middleware decides whether that's a 401 or anonymous.
    """
    token_sources: list[tuple[str, str]] = []

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token_sources.append(("header", authorization[7:].strip()))

    api_key_header = request.headers.get("x-api-key")
    if api_key_header:
        token_sources.append(("header", api_key_header.strip()))

    cookie_token = request.cookies.get(config.cookie_name)
    if cookie_token:
        token_sources.append(("cookie", cookie_token.strip()))

    query_token = request.query_params.get("access_key")
    if query_token:
        token_sources.append(("query", query_token.strip()))

    for source, token in token_sources:
        for configured in config.api_keys:
            if hmac.compare_digest(token, configured.token):
                return AuthResult(
                    identity=AccessIdentity(
                        key_id=configured.key_id,
                        plan=configured.plan,
                        fingerprint=configured.fingerprint,
                    ),
                    bootstrap_token=token if source == "query" else None,
                )

        if tenant_db is not None:
            row = tenant_db.find_active_key_by_token(token)
            if row is not None:
                return AuthResult(
                    identity=AccessIdentity(
                        key_id=row.key_id,
                        plan=row.plan,
                        fingerprint=row.token_display_fingerprint,
                    ),
                    bootstrap_token=token if source == "query" else None,
                )
    return AuthResult(identity=None)


def identity_key(request: Any, identity: AccessIdentity | None) -> tuple[str, str]:
    if identity is not None:
        return f"key:{identity.fingerprint}", identity.plan
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) or "unknown"
    return f"ip:{host}", "anonymous"


class FixedWindowRateLimiter:
    def __init__(self, plan_limits: Mapping[str, RateLimit]) -> None:
        self.plan_limits = dict(plan_limits)
        self._windows: dict[tuple[str, int, int], int] = {}

    def check(self, key: str, plan: str, *, now: float | None = None) -> RateLimitDecision:
        timestamp = int(time.time() if now is None else now)
        limit = self.plan_limits.get(plan) or self.plan_limits["default"]
        window_start = timestamp - (timestamp % limit.window_seconds)
        bucket = (key, limit.window_seconds, window_start)
        count = self._windows.get(bucket, 0) + 1
        self._windows[bucket] = count

        cutoff = timestamp - max(l.window_seconds for l in self.plan_limits.values()) * 2
        self._windows = {
            existing_bucket: existing_count
            for existing_bucket, existing_count in self._windows.items()
            if existing_bucket[2] >= cutoff
        }

        reset_at = window_start + limit.window_seconds
        allowed = count <= limit.limit
        remaining = max(0, limit.limit - count)
        return RateLimitDecision(
            allowed=allowed,
            limit=limit.limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=max(1, reset_at - timestamp),
        )
