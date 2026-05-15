"""End-to-end tests for the POST /commercial/webhook/stripe endpoint.

These run real HTTP requests through the FastAPI TestClient against a
``create_app(...)`` configured with an explicit webhook secret and a
temporary on-disk customer registry. They cover the auth model (signature
is the auth), the failure-status mapping, and the round-trip from a
Stripe-shaped event JSON to a mutated registry file.
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


SECRET = "whsec_test_value"


def _sign(body: bytes, secret: str = SECRET, timestamp: int | None = None) -> dict[str, str]:
    ts = timestamp if timestamp is not None else int(time.time())
    sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=f"{ts}.".encode("utf-8") + body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={sig}"}


def _registry(path: Path) -> None:
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
                        "payment_reference": "INV-2026-001",
                        "monthly_amount": "29.00",
                        "currency": "USD",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _client(tmp_path: Path, *, configured: bool = True):
    from fastapi.testclient import TestClient

    from src.effective_boolean_filter.api import create_app
    from src.effective_boolean_filter.payment_webhook import (
        PaymentWebhookConfig,
    )

    registry = tmp_path / "registry.json"
    _registry(registry)
    ledger_path = tmp_path / "ledger.jsonl"
    if configured:
        config = PaymentWebhookConfig(
            enabled=True,
            stripe_secret=SECRET,
            registry_path=registry,
            ledger_path=ledger_path,
            signature_tolerance_seconds=300,
        )
    else:
        config = PaymentWebhookConfig(
            enabled=False,
            stripe_secret=None,
            registry_path=None,
            ledger_path=None,
            signature_tolerance_seconds=300,
        )
    return TestClient(create_app(payment_webhook_config=config)), registry, ledger_path


def _envelope(event_type: str = "customer.subscription.updated", **object_overrides) -> dict:
    obj = {
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
    obj.update(object_overrides)
    return {"id": "evt_e2e_001", "type": event_type, "data": {"object": obj}}


# ---------------------------------------------------------------------------
# disabled / misconfigured
# ---------------------------------------------------------------------------


def test_webhook_returns_503_when_disabled(tmp_path: Path):
    client, _, _ = _client(tmp_path, configured=False)
    body = json.dumps(_envelope()).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# signature failures
# ---------------------------------------------------------------------------


def test_webhook_rejects_missing_signature_header(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    r = client.post(
        "/commercial/webhook/stripe",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401
    assert "missing" in r.json()["detail"].lower()


def test_webhook_rejects_wrong_signature(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    headers = _sign(body, secret="wrong-secret")
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=headers
    )
    assert r.status_code == 401


def test_webhook_rejects_expired_timestamp(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    # one hour ago — well beyond the 300s tolerance
    headers = _sign(body, timestamp=int(time.time()) - 3600)
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=headers
    )
    assert r.status_code == 401
    assert "tolerance" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# payload failures
# ---------------------------------------------------------------------------


def test_webhook_rejects_non_json_body(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    body = b"this is not json"
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 400


def test_webhook_rejects_payload_missing_customer_id(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    payload = _envelope()
    payload["data"]["object"]["metadata"] = {}
    body = json.dumps(payload).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 400
    assert "customer_id" in r.json()["detail"]


# ---------------------------------------------------------------------------
# successful applies
# ---------------------------------------------------------------------------


def test_webhook_applies_subscription_updated(tmp_path: Path):
    client, registry, ledger_path = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["applied"] is True
    assert payload["action"] == "plan_changed"
    assert payload["customer_id"] == "customer-a"
    # registry mutated to pro
    customer = json.loads(registry.read_text())["customers"][0]
    assert customer["plan"] == "pro"
    # ledger recorded one entry
    lines = ledger_path.read_text().splitlines()
    assert len(lines) == 1


def test_webhook_idempotent_on_replay(tmp_path: Path):
    client, registry, ledger_path = _client(tmp_path)
    body = json.dumps(_envelope()).encode()
    headers = _sign(body)

    first = client.post(
        "/commercial/webhook/stripe", content=body, headers=headers
    )
    second = client.post(
        "/commercial/webhook/stripe", content=body, headers=headers
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["applied"] is True
    assert second.json()["applied"] is False
    assert second.json()["action"] == "duplicate"
    # ledger only grew by one entry; the duplicate replay did not log
    assert len(ledger_path.read_text().splitlines()) == 1


def test_webhook_unknown_event_type_returns_200_ignored(tmp_path: Path):
    """Stripe sends many native event types we don't act on (charge.refunded,
    etc.). They must round-trip as 200 + ``ignored`` so Stripe doesn't
    retry forever."""
    client, _, ledger_path = _client(tmp_path)
    payload = {
        "id": "evt_refund",
        "type": "charge.refunded",
        "data": {"object": {"id": "ch_abc"}},
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 200
    assert r.json()["action"] == "ignored"
    assert r.json()["applied"] is False
    # ledger records ignored events too, for audit
    assert len(ledger_path.read_text().splitlines()) == 1


def test_webhook_rejected_no_customer_returns_200_for_stripe_audit(tmp_path: Path):
    """Unknown customer_id is a Stripe-config bug, not a transport bug.
    We return 200 with ``rejected_no_customer`` so Stripe doesn't keep
    retrying; the ledger entry surfaces it to the operator."""
    client, _, ledger_path = _client(tmp_path)
    payload = _envelope()
    payload["data"]["object"]["metadata"]["customer_id"] = "customer-ghost"
    body = json.dumps(payload).encode()
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 200
    body_json = r.json()
    assert body_json["applied"] is False
    assert body_json["action"] == "rejected_no_customer"
    assert "customer-ghost" in body_json["reason"]


def test_webhook_does_not_require_api_key_in_public_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``EBF_PUBLIC_MODE=1`` would normally 401 every request without a
    bearer token. The webhook endpoint must be exempt because the signature
    is the auth and Stripe doesn't have our API key."""
    from fastapi.testclient import TestClient

    from src.effective_boolean_filter.api import create_app
    from src.effective_boolean_filter.payment_webhook import PaymentWebhookConfig

    registry = tmp_path / "registry.json"
    _registry(registry)
    ledger_path = tmp_path / "ledger.jsonl"
    config = PaymentWebhookConfig(
        enabled=True,
        stripe_secret=SECRET,
        registry_path=registry,
        ledger_path=ledger_path,
        signature_tolerance_seconds=300,
    )
    monkeypatch.setenv("EBF_PUBLIC_MODE", "1")
    monkeypatch.setenv("EBF_API_KEYS", "internal:starter:not-the-webhook-secret")
    client = TestClient(create_app(payment_webhook_config=config))

    body = json.dumps(_envelope()).encode()
    # No Authorization / X-API-Key header at all.
    r = client.post(
        "/commercial/webhook/stripe", content=body, headers=_sign(body)
    )
    assert r.status_code == 200
    assert r.json()["applied"] is True
