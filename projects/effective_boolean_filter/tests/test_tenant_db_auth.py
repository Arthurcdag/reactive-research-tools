"""Auth integration with the SQLite tenant DB.

Covers ``authenticate_request`` falling back to the DB when env-var
keys miss, and the end-to-end public-mode request flow when only the
DB is configured.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


from src.effective_boolean_filter.operations import authenticate_request, load_access_config
from src.effective_boolean_filter.tenant_db import TenantDatabase


class _FakeRequest:
    def __init__(self, token: str | None = None) -> None:
        self.headers = {}
        if token:
            self.headers["authorization"] = f"Bearer {token}"
        self.cookies: dict[str, str] = {}
        self.query_params: dict[str, str] = {}


def test_authenticate_request_resolves_via_tenant_db(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    db.upsert_tenant("customer-a", plan="pro")
    provisioned = db.provision_api_key(tenant_id="customer-a")

    config = load_access_config({"EBF_PUBLIC_MODE": "1"})
    request = _FakeRequest(token=provisioned.token)

    result = authenticate_request(request, config, tenant_db=db)

    assert result.identity is not None
    assert result.identity.key_id == provisioned.key_id
    assert result.identity.plan == "pro"
    assert result.identity.fingerprint == provisioned.token_display_fingerprint


def test_authenticate_request_env_keys_short_circuit_db(tmp_path: Path):
    """An env-var match must win without ever touching the DB. We pass a
    DB whose ``find_active_key_by_token`` would explode if called."""

    class _ExplodingDB:
        def find_active_key_by_token(self, token: str):
            raise RuntimeError("DB must not be consulted on env-key hit")

    config = load_access_config(
        {
            "EBF_PUBLIC_MODE": "1",
            "EBF_API_KEYS": "envkey:starter:env-token-value",
        }
    )
    request = _FakeRequest(token="env-token-value")

    result = authenticate_request(request, config, tenant_db=_ExplodingDB())

    assert result.identity is not None
    assert result.identity.key_id == "envkey"


def test_authenticate_request_returns_none_when_neither_matches(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    config = load_access_config({"EBF_PUBLIC_MODE": "1"})
    request = _FakeRequest(token="totally-unknown-token")
    result = authenticate_request(request, config, tenant_db=db)
    assert result.identity is None


def test_authenticate_request_skips_db_for_empty_token(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    config = load_access_config({"EBF_PUBLIC_MODE": "1"})
    request = _FakeRequest()  # no token at all
    result = authenticate_request(request, config, tenant_db=db)
    assert result.identity is None


def test_revoked_db_key_does_not_authenticate(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    db.upsert_tenant("customer-a", plan="starter")
    provisioned = db.provision_api_key(tenant_id="customer-a")
    db.revoke_api_key(provisioned.key_id)
    config = load_access_config({"EBF_PUBLIC_MODE": "1"})
    request = _FakeRequest(token=provisioned.token)
    result = authenticate_request(request, config, tenant_db=db)
    assert result.identity is None


# ---------------------------------------------------------------------------
# end-to-end through create_app
# ---------------------------------------------------------------------------


def _client(tenant_db: TenantDatabase, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from src.effective_boolean_filter.api import create_app

    for key in (
        "EBF_PUBLIC_MODE",
        "EBF_REQUIRE_API_KEY",
        "EBF_API_KEYS",
        "EBF_TENANT_DB",
        "EBF_REPORT_STORE",
        "EBF_RATE_LIMIT_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EBF_PUBLIC_MODE", "1")
    return TestClient(create_app(tenant_db=tenant_db))


def test_public_mode_authenticates_via_db_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    db.upsert_tenant("customer-a", plan="pro")
    provisioned = db.provision_api_key(tenant_id="customer-a")
    client = _client(db, monkeypatch)

    unauth = client.post(
        "/evaluate_argument", json={"claim": "P", "argument": "P. Therefore P."}
    )
    assert unauth.status_code == 401

    ok = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
        headers={"Authorization": f"Bearer {provisioned.token}"},
    )
    assert ok.status_code == 200
    assert ok.headers["x-ebf-key-id"] == provisioned.key_id
    assert ok.headers["x-ebf-plan"] == "pro"


def test_public_mode_revoked_db_key_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    db.upsert_tenant("customer-a", plan="starter")
    provisioned = db.provision_api_key(tenant_id="customer-a")
    db.revoke_api_key(provisioned.key_id)
    client = _client(db, monkeypatch)
    r = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
        headers={"Authorization": f"Bearer {provisioned.token}"},
    )
    assert r.status_code == 401
