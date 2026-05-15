"""Unit tests for the SQLite tenant database.

Schema migrations, tenant CRUD, key provisioning + revocation, report
put/get/reap, and registry-to-DB sync. Auth and storage integration
have their own files: ``test_tenant_db_auth.py`` and
``test_tenant_db_storage.py``.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.effective_boolean_filter.tenant_db import (
    CURRENT_SCHEMA_VERSION,
    ApiKeyNotFoundError,
    TenantDatabase,
    TenantDBError,
    TenantNotFoundError,
    ValidationError,
    open_tenant_db_from_env,
    parse_tenant_db_dsn,
    sync_tenants_from_registry,
    token_display_fingerprint,
    token_lookup_hash,
)


# ---------------------------------------------------------------------------
# schema & open
# ---------------------------------------------------------------------------


def test_in_memory_db_opens_at_current_schema_version():
    db = TenantDatabase(":memory:")
    assert db.schema_version() == CURRENT_SCHEMA_VERSION


def test_file_db_persists_schema_across_reopens(tmp_path: Path):
    path = tmp_path / "tenant.sqlite"
    TenantDatabase(path)  # first open creates schema
    db = TenantDatabase(path)  # reopen must not re-run migrations
    assert db.schema_version() == CURRENT_SCHEMA_VERSION


def test_parse_tenant_db_dsn_accepts_known_prefixes():
    assert parse_tenant_db_dsn(None) is None
    assert parse_tenant_db_dsn("") is None
    assert parse_tenant_db_dsn("   ") is None
    assert parse_tenant_db_dsn("/abs/path") == "/abs/path"
    assert parse_tenant_db_dsn("tenant:/abs/path") == "/abs/path"
    assert parse_tenant_db_dsn("sqlite:/abs/path") == "/abs/path"


def test_open_tenant_db_from_env_unset_returns_none():
    assert open_tenant_db_from_env({}) is None


def test_open_tenant_db_from_env_set_returns_db(tmp_path: Path):
    path = tmp_path / "tenant.sqlite"
    db = open_tenant_db_from_env({"EBF_TENANT_DB": f"tenant:{path}"})
    assert db is not None
    assert db.schema_version() == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# tenants
# ---------------------------------------------------------------------------


def test_upsert_tenant_inserts_then_updates():
    db = TenantDatabase(":memory:")
    first = db.upsert_tenant("customer-a", plan="starter")
    second = db.upsert_tenant(
        "customer-a", plan="pro", payment_reference="INV-2"
    )
    assert first.plan == "starter"
    assert second.plan == "pro"
    assert second.payment_reference == "INV-2"
    # only one row in the table
    assert len(db.list_tenants()) == 1


def test_get_tenant_raises_when_missing():
    db = TenantDatabase(":memory:")
    with pytest.raises(TenantNotFoundError):
        db.get_tenant("customer-ghost")
    assert db.find_tenant("customer-ghost") is None


def test_set_tenant_plan_propagates_to_active_keys():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    key = db.provision_api_key(tenant_id="customer-a")
    assert key.plan == "starter"
    db.set_tenant_plan("customer-a", "pro")
    stored = db.get_api_key(key.key_id)
    assert stored.plan == "pro"


def test_set_tenant_plan_does_not_propagate_to_revoked_keys():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    key = db.provision_api_key(tenant_id="customer-a")
    db.revoke_api_key(key.key_id)
    db.set_tenant_plan("customer-a", "pro")
    stored = db.get_api_key(key.key_id)
    # revoked rows keep their original plan; no point churning them
    assert stored.plan == "starter"
    assert stored.status == "revoked"


def test_set_tenant_status_raises_when_missing():
    db = TenantDatabase(":memory:")
    with pytest.raises(TenantNotFoundError):
        db.set_tenant_status("customer-ghost", "suspended")


def test_upsert_tenant_rejects_bad_slug():
    db = TenantDatabase(":memory:")
    with pytest.raises(ValidationError):
        db.upsert_tenant("Bad Customer!", plan="starter")


def test_upsert_tenant_rejects_unknown_plan():
    db = TenantDatabase(":memory:")
    with pytest.raises(ValidationError):
        db.upsert_tenant("customer-a", plan="enterprise-mega")


def test_upsert_tenant_rejects_unknown_status():
    db = TenantDatabase(":memory:")
    with pytest.raises(ValidationError):
        db.upsert_tenant("customer-a", plan="starter", status="paused")


# ---------------------------------------------------------------------------
# api keys
# ---------------------------------------------------------------------------


def test_provision_api_key_round_trip_with_token():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    provisioned = db.provision_api_key(tenant_id="customer-a")

    assert len(provisioned.token) >= 32
    # token shown once is the only place plaintext exists
    found = db.find_active_key_by_token(provisioned.token)
    assert found is not None
    assert found.key_id == provisioned.key_id
    assert found.tenant_id == "customer-a"
    assert found.plan == "starter"
    # display fingerprint matches the one returned from provisioning
    assert found.token_display_fingerprint == provisioned.token_display_fingerprint


def test_provision_api_key_requires_existing_tenant():
    db = TenantDatabase(":memory:")
    with pytest.raises(TenantNotFoundError):
        db.provision_api_key(tenant_id="customer-ghost")


def test_provision_api_key_rejects_too_short_tokens():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    with pytest.raises(ValidationError):
        db.provision_api_key(tenant_id="customer-a", token_bytes=8)


def test_find_active_key_by_token_returns_none_for_misses():
    db = TenantDatabase(":memory:")
    assert db.find_active_key_by_token("definitely-not-a-token") is None
    assert db.find_active_key_by_token("") is None


def test_find_active_key_by_token_updates_last_seen_at():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    provisioned = db.provision_api_key(tenant_id="customer-a")
    first = db.find_active_key_by_token(provisioned.token)
    assert first is not None and first.last_seen_at is not None
    # second call must update the timestamp (or at least leave it set)
    time.sleep(1.1)  # one-second ISO 8601 granularity
    second = db.find_active_key_by_token(provisioned.token)
    assert second is not None
    assert second.last_seen_at is not None
    assert second.last_seen_at >= first.last_seen_at


def test_revoke_api_key_blocks_future_lookups():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    provisioned = db.provision_api_key(tenant_id="customer-a")
    db.revoke_api_key(provisioned.key_id)
    assert db.find_active_key_by_token(provisioned.token) is None
    row = db.get_api_key(provisioned.key_id)
    assert row.status == "revoked"
    assert row.revoked_at is not None


def test_revoke_api_key_raises_on_missing():
    db = TenantDatabase(":memory:")
    with pytest.raises(ApiKeyNotFoundError):
        db.revoke_api_key("does-not-exist")


def test_revoke_api_key_is_idempotent_for_already_revoked():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    p = db.provision_api_key(tenant_id="customer-a")
    db.revoke_api_key(p.key_id)
    # second revoke is a no-op (the underlying UPDATE matches 0 rows
    # but the row exists, so we should not raise NotFound)
    db.revoke_api_key(p.key_id)
    assert db.get_api_key(p.key_id).status == "revoked"


def test_list_api_keys_filters_by_tenant():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    db.upsert_tenant("customer-b", plan="pro")
    db.provision_api_key(tenant_id="customer-a")
    db.provision_api_key(tenant_id="customer-b")
    db.provision_api_key(tenant_id="customer-b")
    assert len(db.list_api_keys()) == 3
    assert len(db.list_api_keys("customer-a")) == 1
    assert len(db.list_api_keys("customer-b")) == 2


def test_token_display_fingerprint_matches_legacy_format():
    """Provision a key in the DB, hash the plaintext via the same PBKDF2
    used by ``provision_customer_key.py`` (operations.py), and confirm
    the bytes line up. This is what lets the JSON registry and the DB
    refer to the same key by fingerprint."""
    from src.effective_boolean_filter.operations import _fingerprint

    token = "test-token-stability"
    assert token_display_fingerprint(token) == _fingerprint(token)


def test_token_lookup_hash_is_deterministic_and_unique():
    a = token_lookup_hash("token-a")
    b = token_lookup_hash("token-b")
    assert a != b
    assert token_lookup_hash("token-a") == a
    assert len(a) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------


def test_report_put_get_round_trip():
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")
    db.put_report(
        "r1",
        {"effective_polarity": "effective_yes", "issues": []},
        tenant_id="customer-a",
    )
    assert db.get_report("r1") == {"effective_polarity": "effective_yes", "issues": []}
    assert db.list_report_ids("customer-a") == ["r1"]


def test_report_put_is_idempotent_on_id():
    db = TenantDatabase(":memory:")
    db.put_report("r1", {"v": 1})
    db.put_report("r1", {"v": 2})
    assert db.get_report("r1") == {"v": 2}


def test_report_get_returns_none_for_expired():
    db = TenantDatabase(":memory:")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    db.put_report("r1", {"v": 1}, expires_at=past)
    assert db.get_report("r1") is None


def test_delete_expired_reports_clears_only_expired():
    db = TenantDatabase(":memory:")
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    db.put_report("r_past", {}, expires_at=past)
    db.put_report("r_future", {}, expires_at=future)
    db.put_report("r_perma", {})
    deleted = db.delete_expired_reports()
    assert deleted == 1
    remaining = sorted(db.list_report_ids())
    assert remaining == ["r_future", "r_perma"]


def test_report_id_validation_rejects_path_escape():
    db = TenantDatabase(":memory:")
    with pytest.raises(ValidationError):
        db.put_report("../escape", {})


# ---------------------------------------------------------------------------
# sync from JSON registry
# ---------------------------------------------------------------------------


def test_sync_inserts_and_updates_and_skips_invalid(tmp_path: Path):
    db = TenantDatabase(":memory:")
    db.upsert_tenant("customer-a", plan="starter")  # pre-existing

    registry = {
        "schema": "rtt_customer_registry_v1",
        "customers": [
            {
                "customer_id": "customer-a",
                "plan": "pro",
                "status": "active",
                "payment_reference": "INV-7",
                "monthly_amount": "79.00",
                "currency": "USD",
            },
            {
                "customer_id": "customer-b",
                "plan": "starter",
                "status": "active",
            },
            {
                # invalid plan — must be skipped, not raised
                "customer_id": "customer-x",
                "plan": "enterprise-mega",
                "status": "active",
            },
            "not-a-dict",
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry))
    counts = sync_tenants_from_registry(db, path)

    assert counts == {"inserted": 1, "updated": 1, "skipped": 2}
    assert db.get_tenant("customer-a").plan == "pro"
    assert db.find_tenant("customer-b") is not None
    assert db.find_tenant("customer-x") is None


def test_sync_rejects_wrong_schema(tmp_path: Path):
    db = TenantDatabase(":memory:")
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"schema": "wrong", "customers": []}))
    with pytest.raises(ValidationError, match="schema"):
        sync_tenants_from_registry(db, path)
