"""Smoke tests for ``scripts/tenant_db_admin.py``.

The CLI itself is thin — we exercise it via ``importlib`` (the same
pattern ``test_customer_lifecycle.py`` uses) so we don't depend on
``python`` being on PATH or on the script being installable.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "tenant_db_admin.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("tenant_db_admin", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(argv: list[str], capsys) -> dict:
    module = _load_script()
    rc = module.main(argv)
    out, _err = capsys.readouterr()
    assert rc == 0, f"CLI failed with rc={rc}: {out}"
    return json.loads(out)


def test_tenants_create_and_list(tmp_path: Path, capsys: pytest.CaptureFixture):
    db_path = tmp_path / "tenant.sqlite"
    created = _run(
        ["--db", str(db_path), "tenants", "create",
         "--tenant-id", "customer-a", "--plan", "starter"],
        capsys,
    )
    assert created["tenant_id"] == "customer-a"
    assert created["plan"] == "starter"

    listed = _run(["--db", str(db_path), "tenants", "list"], capsys)
    assert len(listed) == 1
    assert listed[0]["tenant_id"] == "customer-a"


def test_keys_provision_and_revoke(tmp_path: Path, capsys: pytest.CaptureFixture):
    db_path = tmp_path / "tenant.sqlite"
    _run(
        ["--db", str(db_path), "tenants", "create",
         "--tenant-id", "customer-a", "--plan", "starter"],
        capsys,
    )
    provisioned = _run(
        ["--db", str(db_path), "keys", "provision", "--tenant-id", "customer-a"],
        capsys,
    )
    assert provisioned["plan"] == "starter"
    assert provisioned["token"]
    assert "never sees it again" in provisioned["note"]

    revoked = _run(
        ["--db", str(db_path), "keys", "revoke",
         "--key-id", provisioned["key_id"]],
        capsys,
    )
    assert revoked["status"] == "revoked"


def test_set_plan_and_set_status(tmp_path: Path, capsys: pytest.CaptureFixture):
    db_path = tmp_path / "tenant.sqlite"
    _run(
        ["--db", str(db_path), "tenants", "create",
         "--tenant-id", "customer-a", "--plan", "starter"],
        capsys,
    )
    upgraded = _run(
        ["--db", str(db_path), "tenants", "set-plan",
         "--tenant-id", "customer-a", "--plan", "pro"],
        capsys,
    )
    assert upgraded["plan"] == "pro"
    suspended = _run(
        ["--db", str(db_path), "tenants", "set-status",
         "--tenant-id", "customer-a", "--status", "suspended"],
        capsys,
    )
    assert suspended["status"] == "suspended"


def test_sync_from_registry(tmp_path: Path, capsys: pytest.CaptureFixture):
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "rtt_customer_registry_v1",
                "customers": [
                    {"customer_id": "customer-a", "plan": "starter", "status": "active"},
                    {"customer_id": "customer-b", "plan": "pro", "status": "suspended"},
                ],
            }
        )
    )
    db_path = tmp_path / "tenant.sqlite"
    counts = _run(
        ["--db", str(db_path), "sync-from-registry",
         "--registry", str(registry)],
        capsys,
    )
    assert counts == {"inserted": 2, "updated": 0, "skipped": 0}

    listed = _run(["--db", str(db_path), "tenants", "list"], capsys)
    slugs = sorted(t["tenant_id"] for t in listed)
    assert slugs == ["customer-a", "customer-b"]


def test_unknown_tenant_returns_error_code(tmp_path: Path, capsys: pytest.CaptureFixture):
    db_path = tmp_path / "tenant.sqlite"
    module = _load_script()
    rc = module.main(
        ["--db", str(db_path), "tenants", "set-plan",
         "--tenant-id", "customer-ghost", "--plan", "pro"]
    )
    assert rc == 2
    _out, err = capsys.readouterr()
    assert "customer-ghost" in err
