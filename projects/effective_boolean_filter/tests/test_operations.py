"""Production/monetization operational controls."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


ENV_KEYS = (
    "EBF_PUBLIC_MODE",
    "EBF_REQUIRE_API_KEY",
    "EBF_API_KEYS",
    "EBF_AUTH_COOKIE",
    "EBF_COOKIE_SECURE",
    "EBF_RATE_LIMIT_ENABLED",
    "EBF_RATE_LIMIT_DEFAULT",
    "EBF_PLAN_LIMITS",
    "EBF_ENABLE_DOCS",
    "EBF_DISABLE_DOCS",
    "EBF_MAX_BODY_BYTES",
)


def _client(monkeypatch: pytest.MonkeyPatch, **env: str):
    from fastapi.testclient import TestClient
    from src.effective_boolean_filter.api import create_app

    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return TestClient(create_app())


def test_default_app_stays_local_demo_friendly(monkeypatch: pytest.MonkeyPatch):
    client = _client(monkeypatch)
    response = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    )
    assert response.status_code == 200


def test_public_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    client = _client(
        monkeypatch,
        EBF_PUBLIC_MODE="1",
        EBF_API_KEYS="starter-account:starter:secret-token",
    )
    response = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="effective-boolean-filter"'


def test_header_api_key_authenticates_and_marks_plan(monkeypatch: pytest.MonkeyPatch):
    client = _client(
        monkeypatch,
        EBF_PUBLIC_MODE="1",
        EBF_API_KEYS="starter-account:starter:secret-token",
    )
    response = client.get(
        "/commercial/status",
        headers={"X-API-Key": "secret-token"},
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "starter"
    assert response.headers["x-ebf-key-id"] == "starter-account"
    assert response.headers["x-ebf-plan"] == "starter"


def test_query_access_key_bootstraps_dashboard_cookie(monkeypatch: pytest.MonkeyPatch):
    client = _client(
        monkeypatch,
        EBF_PUBLIC_MODE="1",
        EBF_API_KEYS="starter-account:starter:secret-token",
        EBF_COOKIE_SECURE="0",
    )
    dashboard = client.get("/?access_key=secret-token")
    assert dashboard.status_code == 200
    assert "ebf_access_key=" in dashboard.headers.get("set-cookie", "")

    response = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    )
    assert response.status_code == 200


def test_public_mode_disables_docs_by_default(monkeypatch: pytest.MonkeyPatch):
    client = _client(
        monkeypatch,
        EBF_PUBLIC_MODE="1",
        EBF_API_KEYS="starter-account:starter:secret-token",
    )
    assert client.get("/docs", headers={"X-API-Key": "secret-token"}).status_code == 404
    assert client.get("/openapi.json", headers={"X-API-Key": "secret-token"}).status_code == 404


def test_rate_limit_enforces_plan_limit(monkeypatch: pytest.MonkeyPatch):
    client = _client(
        monkeypatch,
        EBF_PUBLIC_MODE="1",
        EBF_API_KEYS="starter-account:starter:secret-token",
        EBF_PLAN_LIMITS="starter=1/minute",
    )
    headers = {"X-API-Key": "secret-token"}
    first = client.get("/commercial/status", headers=headers)
    second = client.get("/commercial/status", headers=headers)
    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "1"
    assert second.status_code == 429
    assert second.headers["retry-after"]


def test_commercial_and_legal_surfaces_are_public(monkeypatch: pytest.MonkeyPatch):
    client = _client(monkeypatch, EBF_PUBLIC_MODE="1", EBF_API_KEYS="paid:pro:secret-token")
    plans = client.get("/commercial/plans")
    terms = client.get("/legal/terms")
    privacy = client.get("/legal/privacy")
    assert plans.status_code == 200
    assert {plan["slug"] for plan in plans.json()["plans"]} >= {"starter", "pro", "enterprise"}
    assert terms.status_code == 200
    assert privacy.status_code == 200


# ---------------------------------------------------------------------------
# request body-size limit
# ---------------------------------------------------------------------------

def test_oversized_request_body_rejected_with_413(monkeypatch: pytest.MonkeyPatch):
    """A body whose Content-Length exceeds the configured limit is rejected
    before auth, rate limiting, or Pydantic ever runs."""
    client = _client(monkeypatch, EBF_MAX_BODY_BYTES="2048")
    response = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. " * 2000},  # well over 2 KB
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]
    # the baseline security headers still go out on the rejection
    assert response.headers["x-content-type-options"] == "nosniff"


def test_body_within_limit_still_processed(monkeypatch: pytest.MonkeyPatch):
    client = _client(monkeypatch, EBF_MAX_BODY_BYTES="65536")
    response = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    )
    assert response.status_code == 200


def test_body_limit_short_circuits_before_auth(monkeypatch: pytest.MonkeyPatch):
    """In public mode an oversized body returns 413, not 401 — the size
    guard runs first so an attacker cannot make the server buffer a huge
    payload just to then reject it for missing a key."""
    client = _client(
        monkeypatch,
        EBF_PUBLIC_MODE="1",
        EBF_API_KEYS="starter-account:starter:secret-token",
        EBF_MAX_BODY_BYTES="2048",
    )
    response = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. " * 2000},
    )
    assert response.status_code == 413


def test_default_body_limit_accepts_a_maxed_out_score_probes_body(
    monkeypatch: pytest.MonkeyPatch,
):
    """The default ceiling must never reject a body Pydantic would accept.
    A fully loaded /score_probe_results body (20 answers at max field
    sizes) is the widest engine payload; it must pass the size guard and
    then succeed."""
    client = _client(monkeypatch)
    answers = [
        {"question": "q" * 1000, "passed": True, "answer": "a" * 4000}
        for _ in range(20)
    ]
    response = client.post(
        "/score_probe_results",
        json={"claim": "P", "argument": "P. Therefore P.", "answers": answers},
    )
    assert response.status_code == 200


def test_invalid_max_body_bytes_is_a_visible_misconfiguration():
    """A sub-floor or unparseable EBF_MAX_BODY_BYTES raises rather than
    silently degrading to a value that would reject ordinary traffic."""
    from src.effective_boolean_filter.operations import (
        DEFAULT_MAX_BODY_BYTES,
        load_access_config,
        parse_max_body_bytes,
    )

    assert parse_max_body_bytes(None) == DEFAULT_MAX_BODY_BYTES
    assert parse_max_body_bytes("  ") == DEFAULT_MAX_BODY_BYTES
    assert parse_max_body_bytes("4096") == 4096
    with pytest.raises(ValueError, match="floor"):
        parse_max_body_bytes("512")
    with pytest.raises(ValueError, match="positive integer"):
        parse_max_body_bytes("not-a-number")
    with pytest.raises(ValueError):
        load_access_config({"EBF_MAX_BODY_BYTES": "0"})
