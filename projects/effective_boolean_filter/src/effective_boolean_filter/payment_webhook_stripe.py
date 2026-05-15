"""Stripe-specific webhook signature verification and event parsing.

Two responsibilities, kept in one file because they only make sense as a
pair:

* :func:`verify_stripe_signature` validates the ``Stripe-Signature``
  header against the raw request body using HMAC-SHA256.
* :func:`parse_stripe_event` converts a Stripe event JSON object into
  the provider-neutral :class:`payment_webhook.PaymentEvent` used by the
  applier.

The applier (``apply_payment_event``) lives in :mod:`payment_webhook`
and is intentionally provider-agnostic, so a second adapter (Mercado
Pago, invoice CSV import, etc.) can be added without touching the apply
path. Only the parse + signature halves are Stripe-shaped.

The mapping between Stripe subscription metadata and the local
``rtt_customer_registry_v1`` is **metadata-driven**: the Stripe
subscription must have ``metadata.customer_id`` set to the local
registry slug. Plan is taken from ``metadata.plan`` first, then from
the first item's ``price.lookup_key`` as a fallback (Stripe-native — set
the lookup_key on each Price to the plan slug to avoid touching
metadata). This avoids maintaining a separate ``cus_...`` -> slug
mapping table on our side.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Mapping

from .payment_webhook import (
    PaymentEvent,
    WebhookPayloadError,
    WebhookSignatureError,
)


STRIPE_PROVIDER = "stripe"


# Stripe native event types we know how to act on, plus the neutral
# event type each one maps to. Any native type not in this table maps to
# the neutral ``ignored`` event type so the webhook returns 200 (Stripe
# only re-sends on non-2xx) and the ledger records the visit.
_STRIPE_EVENT_TYPE_MAP: Mapping[str, str] = {
    "checkout.session.completed": "subscription_activated",
    "customer.subscription.created": "subscription_activated",
    "customer.subscription.updated": "subscription_updated",
    "customer.subscription.deleted": "subscription_canceled",
    "invoice.payment_failed": "payment_failed",
    "invoice.payment_succeeded": "payment_succeeded",
}


# ---------------------------------------------------------------------------
# signature
# ---------------------------------------------------------------------------


def _parse_signature_header(header: str) -> tuple[int, list[str]]:
    """Return ``(timestamp, [v1_signatures, ...])``.

    Stripe's header looks like::

        t=1492774577,v1=<hex>,v1=<hex>

    The ``v0`` value is deprecated; we ignore it. Multiple ``v1`` values
    happen during webhook-secret rotation — we accept the request if any
    of them verifies.
    """
    if not header or not header.strip():
        raise WebhookSignatureError("missing Stripe-Signature header")

    timestamp: int | None = None
    v1_signatures: list[str] = []
    for part in header.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise WebhookSignatureError(
                    "Stripe-Signature timestamp is not an integer"
                ) from exc
        elif key == "v1":
            if value:
                v1_signatures.append(value)
        # v0 and any unknown scheme are intentionally ignored.

    if timestamp is None:
        raise WebhookSignatureError("Stripe-Signature missing 't' timestamp")
    if not v1_signatures:
        raise WebhookSignatureError("Stripe-Signature missing 'v1' signature")
    return timestamp, v1_signatures


def verify_stripe_signature(
    *,
    payload: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> int:
    """Verify the ``Stripe-Signature`` header against ``payload``.

    Returns the event timestamp on success. Raises
    :class:`WebhookSignatureError` on any verification failure.

    The signed payload Stripe documents is ``f"{t}.{raw_body}"`` where
    ``raw_body`` is the exact bytes that arrived in the HTTP request —
    re-serialising via ``json.dumps`` will produce a different byte
    string and break verification. The endpoint must therefore pass the
    raw body through.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise WebhookSignatureError("verify_stripe_signature: payload must be bytes")
    if not secret:
        raise WebhookSignatureError(
            "verify_stripe_signature: webhook secret is required"
        )
    if tolerance_seconds < 1:
        raise WebhookSignatureError(
            "verify_stripe_signature: tolerance_seconds must be positive"
        )

    timestamp, signatures = _parse_signature_header(signature_header)
    current = time.time() if now is None else now
    if abs(int(current) - timestamp) > tolerance_seconds:
        raise WebhookSignatureError(
            f"Stripe-Signature timestamp {timestamp} is outside the "
            f"{tolerance_seconds}-second tolerance window"
        )

    signed_payload = f"{timestamp}.".encode("utf-8") + bytes(payload)
    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=signed_payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    for candidate in signatures:
        if hmac.compare_digest(expected, candidate):
            return timestamp
    raise WebhookSignatureError("Stripe-Signature v1 signatures did not match")


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


def _require_str(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebhookPayloadError(f"Stripe payload missing {what}")
    return value.strip()


def _maybe_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _stripe_object(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise WebhookPayloadError("Stripe payload must be a JSON object")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise WebhookPayloadError("Stripe payload missing data object")
    obj = data.get("object")
    if not isinstance(obj, Mapping):
        raise WebhookPayloadError("Stripe payload missing data.object")
    return obj


def _derive_plan(obj: Mapping[str, Any]) -> str | None:
    """Pull the local plan slug from a Stripe subscription/checkout object.

    Priority order:
      1. ``metadata.plan`` (explicit override)
      2. first item's ``price.lookup_key`` (Stripe-native)
      3. None — the caller decides whether plan is required for this
         event type.
    """
    metadata = obj.get("metadata")
    if isinstance(metadata, Mapping):
        plan = metadata.get("plan")
        if isinstance(plan, str) and plan.strip():
            return plan.strip()

    items = obj.get("items")
    if isinstance(items, Mapping):
        data_list = items.get("data")
        if isinstance(data_list, list) and data_list:
            first = data_list[0]
            if isinstance(first, Mapping):
                price = first.get("price")
                if isinstance(price, Mapping):
                    lookup_key = price.get("lookup_key")
                    if isinstance(lookup_key, str) and lookup_key.strip():
                        return lookup_key.strip()
    return None


def _derive_customer_id(obj: Mapping[str, Any], event_type: str) -> str:
    """Resolve the local registry slug for a Stripe event.

    Stripe's own ``customer`` field is ``cus_...`` — not the local slug.
    The operator must set ``metadata.customer_id`` on the subscription
    (or checkout session) to the local slug; we refuse to guess.
    Missing metadata is a configuration bug, surfaced as a 400.
    """
    metadata = obj.get("metadata")
    if isinstance(metadata, Mapping):
        cid = metadata.get("customer_id")
        if isinstance(cid, str) and cid.strip():
            return cid.strip()
    raise WebhookPayloadError(
        f"Stripe {event_type} object is missing metadata.customer_id; set it on "
        "the subscription (or checkout session) to the local registry slug"
    )


def _derive_monthly_amount(obj: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(monthly_amount, currency)`` from a Stripe object, or ``("", "")``.

    Stripe uses minor units (e.g. cents), so we divide by 100 and format
    with two decimals. We don't try to handle non-decimal currencies
    (JPY etc. — Stripe uses zero-decimal there) here; the operator can
    override via the script if precision matters for billing.
    """
    plan = obj.get("plan")
    if isinstance(plan, Mapping):
        amount = plan.get("amount")
        currency = plan.get("currency")
        if isinstance(amount, int) and isinstance(currency, str):
            return (f"{amount / 100:.2f}", currency.strip().upper())

    items = obj.get("items")
    if isinstance(items, Mapping):
        data_list = items.get("data")
        if isinstance(data_list, list) and data_list:
            first = data_list[0]
            if isinstance(first, Mapping):
                price = first.get("price")
                if isinstance(price, Mapping):
                    unit = price.get("unit_amount")
                    currency = price.get("currency")
                    if isinstance(unit, int) and isinstance(currency, str):
                        return (f"{unit / 100:.2f}", currency.strip().upper())
    return ("", "")


def parse_stripe_event(payload: Mapping[str, Any]) -> PaymentEvent:
    """Translate a Stripe event into a provider-neutral :class:`PaymentEvent`.

    Stripe sends one well-known JSON envelope::

        {"id": "evt_...", "type": "...", "data": {"object": {...}}, ...}

    We pull the event id and type from the envelope, and everything else
    from ``data.object`` via the helpers above.
    """
    if not isinstance(payload, Mapping):
        raise WebhookPayloadError("Stripe payload must be a JSON object")

    event_id = _require_str(payload.get("id"), "id")
    native_type = _require_str(payload.get("type"), "type")
    neutral_type = _STRIPE_EVENT_TYPE_MAP.get(native_type, "ignored")

    if neutral_type == "ignored":
        # We don't even read data.object for ignored types — Stripe sends
        # plenty of envelope-only events (charge.refunded etc.) that we
        # don't act on, and forcing them through the metadata check
        # would 4xx them and make Stripe re-try forever.
        return PaymentEvent(
            provider=STRIPE_PROVIDER,
            event_id=event_id,
            event_type="ignored",
            customer_id="",
            note=f"stripe.{native_type}",
            raw={"id": event_id, "type": native_type},
        )

    obj = _stripe_object(payload)
    customer_id = _derive_customer_id(obj, native_type)
    plan = _derive_plan(obj)
    monthly_amount, currency = _derive_monthly_amount(obj)
    invoice_id = _maybe_str(obj.get("id"))
    payment_reference = f"stripe:{invoice_id}" if invoice_id else f"stripe:{event_id}"

    # On a subscription.updated, Stripe puts the new subscription status
    # on the object (active / past_due / unpaid / canceled). We honour it
    # only when it maps cleanly to our registry's status vocabulary;
    # otherwise we let the event_type drive the new status.
    status: str | None = None
    if neutral_type == "subscription_updated":
        native_status = _maybe_str(obj.get("status"))
        if native_status == "active":
            status = "active"
        elif native_status == "canceled":
            status = "canceled"
        elif native_status in ("past_due", "unpaid", "incomplete_expired"):
            status = "suspended"

    return PaymentEvent(
        provider=STRIPE_PROVIDER,
        event_id=event_id,
        event_type=neutral_type,
        customer_id=customer_id,
        plan=plan,
        status=status,
        payment_reference=payment_reference,
        monthly_amount=monthly_amount,
        currency=currency,
        note=f"stripe.{native_type}",
        raw={"id": event_id, "type": native_type},
    )


__all__ = [
    "STRIPE_PROVIDER",
    "parse_stripe_event",
    "verify_stripe_signature",
]
