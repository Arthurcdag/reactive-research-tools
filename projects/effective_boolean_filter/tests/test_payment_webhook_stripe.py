"""Unit tests for the Stripe webhook adapter.

Two halves: signature verification and event-shape parsing. Both happen
before the provider-neutral apply step (which is tested in
``test_payment_webhook.py``).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from src.effective_boolean_filter.payment_webhook import WebhookPayloadError
from src.effective_boolean_filter.payment_webhook_stripe import (
    STRIPE_PROVIDER,
    parse_stripe_event,
    verify_stripe_signature,
)


# ---------------------------------------------------------------------------
# signature helpers
# ---------------------------------------------------------------------------


SECRET = "whsec_test_secret_value"


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    """Build a Stripe-style signature header with one v1 entry.

    We construct the signature exactly the same way Stripe documents it
    so the verifier under test is doing the inverse operation and the
    pass/fail in tests reflects real behaviour, not a self-referential
    helper.
    """
    sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=f"{timestamp}.".encode("utf-8") + payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={sig}"


# ---------------------------------------------------------------------------
# verify_stripe_signature
# ---------------------------------------------------------------------------


def test_verify_accepts_good_signature():
    body = b'{"id":"evt_test"}'
    now = int(time.time())
    header = _sign(body, SECRET, now)
    returned = verify_stripe_signature(
        payload=body, signature_header=header, secret=SECRET, now=now
    )
    assert returned == now


def test_verify_rejects_missing_header():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    with pytest.raises(WebhookSignatureError, match="missing"):
        verify_stripe_signature(
            payload=b"{}", signature_header="", secret=SECRET, now=1
        )


def test_verify_rejects_missing_timestamp():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    with pytest.raises(WebhookSignatureError, match="'t'"):
        verify_stripe_signature(
            payload=b"{}",
            signature_header="v1=deadbeef",
            secret=SECRET,
            now=1,
        )


def test_verify_rejects_non_integer_timestamp():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    with pytest.raises(WebhookSignatureError, match="integer"):
        verify_stripe_signature(
            payload=b"{}",
            signature_header="t=now,v1=deadbeef",
            secret=SECRET,
            now=1,
        )


def test_verify_rejects_missing_v1():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    with pytest.raises(WebhookSignatureError, match="'v1'"):
        verify_stripe_signature(
            payload=b"{}",
            signature_header="t=1,v0=deadbeef",
            secret=SECRET,
            now=1,
        )


def test_verify_rejects_expired_timestamp():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    body = b"{}"
    issued_at = 1000
    header = _sign(body, SECRET, issued_at)
    with pytest.raises(WebhookSignatureError, match="tolerance"):
        verify_stripe_signature(
            payload=body,
            signature_header=header,
            secret=SECRET,
            tolerance_seconds=60,
            now=issued_at + 120,
        )


def test_verify_rejects_wrong_signature():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    body = b'{"id":"evt_test"}'
    bad_header = "t=1,v1=" + "0" * 64
    with pytest.raises(WebhookSignatureError, match="did not match"):
        verify_stripe_signature(
            payload=body, signature_header=bad_header, secret=SECRET, now=1
        )


def test_verify_rejects_signature_when_body_tampered():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    original = b'{"id":"evt_test","type":"customer.subscription.updated"}'
    header = _sign(original, SECRET, 1)
    tampered = original.replace(b"updated", b"deleted")
    with pytest.raises(WebhookSignatureError):
        verify_stripe_signature(
            payload=tampered, signature_header=header, secret=SECRET, now=1
        )


def test_verify_accepts_either_v1_during_rotation():
    body = b"{}"
    timestamp = 100
    # Build the header with one wrong v1 then one good v1 — a rotation
    # window where Stripe sends both old and new signatures.
    bad = "0" * 64
    good = hmac.new(
        SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    header = f"t={timestamp},v1={bad},v1={good}"
    returned = verify_stripe_signature(
        payload=body, signature_header=header, secret=SECRET, now=timestamp
    )
    assert returned == timestamp


def test_verify_rejects_empty_secret():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    with pytest.raises(WebhookSignatureError, match="secret"):
        verify_stripe_signature(
            payload=b"{}", signature_header="t=1,v1=x", secret="", now=1
        )


def test_verify_rejects_non_bytes_payload():
    from src.effective_boolean_filter.payment_webhook import WebhookSignatureError

    with pytest.raises(WebhookSignatureError, match="bytes"):
        verify_stripe_signature(
            payload="{}",  # type: ignore[arg-type]
            signature_header="t=1,v1=x",
            secret=SECRET,
            now=1,
        )


# ---------------------------------------------------------------------------
# parse_stripe_event
# ---------------------------------------------------------------------------


def _subscription_envelope(event_type: str, **object_overrides):
    obj = {
        "id": "sub_abc",
        "customer": "cus_stripe_xyz",
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
    return {
        "id": "evt_001",
        "type": event_type,
        "data": {"object": obj},
    }


def test_parse_subscription_created_maps_to_activated():
    event = parse_stripe_event(_subscription_envelope("customer.subscription.created"))
    assert event.provider == STRIPE_PROVIDER
    assert event.event_type == "subscription_activated"
    assert event.customer_id == "customer-a"
    assert event.plan == "pro"


def test_parse_subscription_updated_carries_native_status():
    payload = _subscription_envelope("customer.subscription.updated", status="past_due")
    event = parse_stripe_event(payload)
    assert event.event_type == "subscription_updated"
    assert event.status == "suspended"


def test_parse_subscription_updated_passes_active_through():
    payload = _subscription_envelope("customer.subscription.updated", status="active")
    event = parse_stripe_event(payload)
    assert event.status == "active"


def test_parse_subscription_deleted_maps_to_canceled():
    event = parse_stripe_event(_subscription_envelope("customer.subscription.deleted"))
    assert event.event_type == "subscription_canceled"


def test_parse_invoice_payment_failed_maps_to_payment_failed():
    payload = {
        "id": "evt_invoice",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "in_abc",
                "metadata": {"customer_id": "customer-a"},
            }
        },
    }
    event = parse_stripe_event(payload)
    assert event.event_type == "payment_failed"
    assert event.payment_reference == "stripe:in_abc"


def test_parse_invoice_payment_succeeded_maps_to_payment_succeeded():
    payload = {
        "id": "evt_invoice_ok",
        "type": "invoice.payment_succeeded",
        "data": {"object": {"id": "in_xyz", "metadata": {"customer_id": "customer-a"}}},
    }
    event = parse_stripe_event(payload)
    assert event.event_type == "payment_succeeded"


def test_parse_unknown_type_maps_to_ignored_without_metadata_check():
    """Stripe sends many native event types we don't act on. They must
    parse as ``ignored`` even when ``data.object.metadata`` is absent,
    so we don't 4xx Stripe into a retry loop on harmless events."""
    payload = {
        "id": "evt_refund",
        "type": "charge.refunded",
        "data": {"object": {"id": "ch_abc"}},
    }
    event = parse_stripe_event(payload)
    assert event.event_type == "ignored"
    assert event.customer_id == ""


def test_parse_falls_back_to_price_lookup_key_when_metadata_plan_absent():
    payload = _subscription_envelope("customer.subscription.updated")
    # remove the metadata.plan but keep metadata.customer_id
    payload["data"]["object"]["metadata"] = {"customer_id": "customer-a"}
    event = parse_stripe_event(payload)
    assert event.plan == "pro"  # from price.lookup_key


def test_parse_requires_customer_id_for_non_ignored_event():
    payload = _subscription_envelope("customer.subscription.updated")
    payload["data"]["object"]["metadata"] = {}  # missing customer_id
    with pytest.raises(WebhookPayloadError, match="customer_id"):
        parse_stripe_event(payload)


def test_parse_derives_monthly_amount_from_unit_amount():
    payload = _subscription_envelope("customer.subscription.created")
    event = parse_stripe_event(payload)
    # unit_amount=14900 / 100 -> 149.00
    assert event.monthly_amount == "149.00"
    assert event.currency == "USD"


def test_parse_rejects_non_dict_payload():
    with pytest.raises(WebhookPayloadError, match="JSON object"):
        parse_stripe_event(json.loads("[1,2,3]"))


def test_parse_rejects_missing_id_or_type():
    with pytest.raises(WebhookPayloadError, match="id"):
        parse_stripe_event({"type": "x", "data": {"object": {}}})
    with pytest.raises(WebhookPayloadError, match="type"):
        parse_stripe_event({"id": "evt_x", "data": {"object": {}}})


def test_parse_rejects_missing_data_object_for_actioned_event():
    with pytest.raises(WebhookPayloadError):
        parse_stripe_event(
            {"id": "evt_x", "type": "customer.subscription.updated"}
        )
