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
