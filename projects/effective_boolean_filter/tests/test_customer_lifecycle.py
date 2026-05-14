"""No-secret customer lifecycle updates."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "customer_lifecycle.py"


def _module():
    spec = importlib.util.spec_from_file_location("customer_lifecycle", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_update_customer_records_status_change_without_token():
    module = _module()
    data = {
        "schema": "rtt_customer_registry_v1",
        "customers": [
            {
                "customer_id": "customer-a",
                "plan": "starter",
                "status": "active",
                "key_fingerprint": "abc123",
                "token": "must-not-matter",
            }
        ],
    }
    customer = module.update_customer(
        data,
        customer_id="customer-a",
        status="suspended",
        monthly_amount="39",
        currency="brl",
        note="payment failed",
    )
    assert customer["status"] == "suspended"
    assert customer["monthly_amount"] == "39.00"
    assert customer["currency"] == "BRL"
    assert customer["updated_at"]
    assert customer["events"][-1]["event"] == "status:suspended,monthly_amount,currency"
    assert customer["events"][-1]["note"] == "payment failed"
    assert customer["token"] == "must-not-matter"


def test_update_customer_rejects_unknown_customer():
    module = _module()
    data = {"schema": "rtt_customer_registry_v1", "customers": []}
    with pytest.raises(ValueError, match="customer not found"):
        module.update_customer(data, customer_id="missing", status="active")


def test_cli_persists_no_secret_lifecycle_update(tmp_path, capsys):
    module = _module()
    registry = tmp_path / "customer_registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "rtt_customer_registry_v1",
                "customers": [
                    {
                        "customer_id": "customer-a",
                        "plan": "starter",
                        "status": "active",
                        "key_fingerprint": "abc123",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code = module.main(
        [
            "--registry-file",
            str(registry),
            "--customer-id",
            "customer-a",
            "--status",
            "canceled",
            "--monthly-amount",
            "0",
            "--currency",
            "brl",
            "--note",
            "customer requested cancellation",
        ]
    )

    assert code == 0
    output = capsys.readouterr().out
    saved = json.loads(registry.read_text(encoding="utf-8"))
    customer = saved["customers"][0]
    assert "updated_customer=" in output
    assert customer["status"] == "canceled"
    assert customer["monthly_amount"] == "0.00"
    assert customer["currency"] == "BRL"
    assert customer["events"][-1]["note"] == "customer requested cancellation"
    assert "token" not in registry.read_text(encoding="utf-8")
