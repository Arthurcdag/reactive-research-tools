"""Payment webhook → tenant DB mirror.

These tests cover the end-to-end path: signed Stripe webhook arrives,
the JSON registry is mutated by ``apply_payment_event``, and (when a
tenant DB is configured) the corresponding row in ``tenants`` is
upserted to match. The DB mirror is intentionally best-effort: a DB
failure must not break the webhook contract.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


SECRET = "whsec_tenant_db_test"


def _sign(body: bytes, secret: str = SECRET, timestamp: int | None = None) -> dict[str, str]:
    ts = timestamp if timestamp is not None else int(time.time())
    sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=f"{ts}.".encode("utf-8") + body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={sig}"}


def _seed_registry(path: Path) -> None:
    path.write_text(
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
            },
            indent=2,
        )
    )


def _envelope() -> dict:
    return {
        "id": "evt_dbsync_001",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_abc",
                "customer": "cus_xyz",
                "status": "active",
                "metadata": {"customer_id": "customer-a", "plan": "pro"},
                "items": {
                    "data": [
                        {
                            "price": {
                                "lookup_key": "pro",
                                "unit_amount": 14900,
                                "currency": "usd",
                            }
                        }
                    ]
                },
            }
        },
    }


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from src.effective_boolean_filter.api import create_app
    from src.effective_boolean_filter.payment_webhook import PaymentWebhookConfig
    from src.effective_boolean_filter.tenant_db import TenantDatabase

    registry = tmp_path / "registry.json"
    _seed_registry(registry)
    ledger_path = tmp_path / "ledger.jsonl"
    db = TenantDatabase(tmp_path / "tenant.sqlite")

    config = PaymentWebhookConfig(
        enabled=True,
        stripe_secret=SECRET,
        registry_path=registry,
        ledger_path=ledger_path,
        signature_tolerance_seconds=300,
    )
    return (
        TestClient(create_app(payment_webhook_config=config, tenant_db=db)),
        registry,
        db,
    )


def test_webhook_upserts_tenant_when_db_configured(tmp_path: Path):
    """A first-time Stripe webhook event should insert the tenant row
    (with the new plan) into the DB, even though the tenant was only in
    the JSON registry before."""
    client, registry, db = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 200
    assert r.json()["applied"] is True

    # JSON registry mutated…
    customer = json.loads(registry.read_text())["customers"][0]
    assert customer["plan"] == "pro"
    # …and the DB row was created/updated to match.
    tenant = db.get_tenant("customer-a")
    assert tenant.plan == "pro"
    assert tenant.status == "active"


def test_webhook_does_not_touch_db_on_rejected_event(tmp_path: Path):
    """An event whose customer is not in the registry must not create a
    row in the DB either — the DB is a derived view, not a source of
    new identities."""
    client, _, db = _client(tmp_path)
    payload = _envelope()
    payload["data"]["object"]["metadata"]["customer_id"] = "customer-ghost"
    body = json.dumps(payload).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 200
    assert r.json()["action"] == "rejected_no_customer"
    assert db.find_tenant("customer-ghost") is None


def test_webhook_does_not_touch_db_on_duplicate(tmp_path: Path):
    client, _, db = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    headers = _sign(body)

    client.post("/commercial/webhook/stripe", content=body, headers=headers)
    # capture state, replay, compare
    tenant_after_first = db.get_tenant("customer-a")
    second = client.post(
        "/commercial/webhook/stripe", content=body, headers=headers
    )
    assert second.json()["action"] == "duplicate"
    tenant_after_replay = db.get_tenant("customer-a")
    # The duplicate replay must not bump updated_at on the DB tenant
    # — the mirror is gated on applied=True.
    assert tenant_after_replay.updated_at == tenant_after_first.updated_at
