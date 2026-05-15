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

# Pre-validation request-body ceiling. This is a denial-of-service guard,
# not a correctness control: Pydantic's per-field limits remain the real
# input contract. The ceiling is set comfortably above the largest body
# any endpoint's Pydantic model can legitimately accept (the widest is
# ``/advisory/nyahlothep`` with 20 full candidates, ~280 KB), so it never
# rejects a request Pydantic would have accepted. It only stops an
# attacker streaming a multi-megabyte payload that the server would
# otherwise buffer and hand to Pydantic before rejection.
#
# Header-based: it inspects ``Content-Length`` and so does not cover
# chunked requests with no declared length. A reverse proxy body-size cap
# is still the recommended outer control for public deployments.
DEFAULT_MAX_BODY_BYTES = 512 * 1024
_MIN_MAX_BODY_BYTES = 1024


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
    max_body_bytes: int


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


def parse_max_body_bytes(value: str | None) -> int:
    """Parse the ``EBF_MAX_BODY_BYTES`` override.

    Unset/blank uses :data:`DEFAULT_MAX_BODY_BYTES`. A value below
    :data:`_MIN_MAX_BODY_BYTES` would reject ordinary requests, so it is
    rejected as a misconfiguration rather than silently clamped.
    """
    if value is None or not value.strip():
        return DEFAULT_MAX_BODY_BYTES
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"invalid EBF_MAX_BODY_BYTES {value!r}; expected a positive integer"
        ) from exc
    if parsed < _MIN_MAX_BODY_BYTES:
        raise ValueError(
            f"EBF_MAX_BODY_BYTES {parsed} is below the {_MIN_MAX_BODY_BYTES}-byte "
            "floor; that would reject ordinary requests"
        )
    return parsed


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
        max_body_bytes=parse_max_body_bytes(source.get("EBF_MAX_BODY_BYTES")),
    )


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS


def content_length_over_limit(request: Any, limit_bytes: int) -> int | None:
    """Return the declared body size when it exceeds ``limit_bytes``.

    Returns ``None`` when the request is within the limit, has no
    ``Content-Length`` header, or declares an unparseable length — those
    cases fall through to Pydantic's per-field validation. The header
    check exists to reject an oversized payload *before* the server
    buffers it; it is a fast-path guard, not the only line of defence.
    """
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        length = int(raw)
    except (TypeError, ValueError):
        return None
    if length > limit_bytes:
        return length
    return None


def authenticate_request(request: Any, config: AccessConfig) -> AuthResult:
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
