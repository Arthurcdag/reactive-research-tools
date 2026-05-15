"""TenantReportStore tests + DSN selection via :func:`get_store`."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.effective_boolean_filter.storage import (
    FileStore,
    InMemoryStore,
    TenantReportStore,
    get_store,
)
from src.effective_boolean_filter.tenant_db import TenantDatabase


def test_tenant_report_store_put_get_round_trip(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    db.upsert_tenant("customer-a", plan="starter")
    store = TenantReportStore(db, default_tenant_id="customer-a")
    store.put("r1", {"effective_polarity": "effective_yes"})
    assert store.get("r1") == {"effective_polarity": "effective_yes"}
    assert "r1" in store
    assert store.list_ids() == ["r1"]


def test_tenant_report_store_missing_returns_none(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    store = TenantReportStore(db)
    assert store.get("does-not-exist") is None
    assert "does-not-exist" not in store


def test_tenant_report_store_rejects_path_escape(tmp_path: Path):
    db = TenantDatabase(tmp_path / "tenant.sqlite")
    store = TenantReportStore(db)
    with pytest.raises(ValueError):
        store.put("../escape", {})


def test_get_store_tenant_dsn_returns_tenant_report_store(tmp_path: Path):
    spec = f"tenant:{tmp_path / 'tenant.sqlite'}"
    store = get_store(spec)
    assert isinstance(store, TenantReportStore)


def test_get_store_falls_back_to_memory_when_unset():
    assert isinstance(get_store(""), InMemoryStore)


def test_get_store_file_dsn_still_works(tmp_path: Path):
    store = get_store(f"file:{tmp_path / 'reports'}")
    assert isinstance(store, FileStore)


def test_get_store_tenant_dsn_requires_path():
    with pytest.raises(ValueError, match="SQLite path"):
        get_store("tenant:")


def test_get_store_rejects_unknown_dsn():
    with pytest.raises(ValueError, match="unknown"):
        get_store("redis:/etc")
