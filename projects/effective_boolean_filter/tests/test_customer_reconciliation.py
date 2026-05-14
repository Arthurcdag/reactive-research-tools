"""No-secret customer reconciliation reports."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "customer_reconciliation.py"


def _module():
    spec = importlib.util.spec_from_file_location("customer_reconciliation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reconciliation_report_excludes_tokens():
    module = _module()
    data = {
        "schema": "rtt_customer_registry_v1",
        "customers": [
            {
                "customer_id": "customer-a",
                "plan": "starter",
                "status": "active",
                "payment_reference": "INV-001",
                "contracting_entity": "brazil-entity",
                "key_fingerprint": "abc123",
                "created_at": "2026-05-14T00:00:00+00:00",
                "token": "must-not-render",
            }
        ],
    }
    report = module.render_markdown(data, title="Conka8 Monthly Reconciliation")
    assert "Conka8 Monthly Reconciliation" in report
    assert "customer-a" in report
    assert "INV-001" in report
    assert "abc123" in report
    assert "must-not-render" not in report


def test_customer_rows_sort_stably():
    module = _module()
    data = {
        "schema": "rtt_customer_registry_v1",
        "customers": [
            {"customer_id": "zeta", "plan": "pro", "status": "active"},
            {"customer_id": "alpha", "plan": "starter", "status": "active"},
        ],
    }
    rows = module.customer_rows(data)
    assert [row["customer_id"] for row in rows] == ["alpha", "zeta"]
