"""Provider-neutral payment-webhook engine.

The webhook flow is intentionally split into three layers:

* **Provider adapter** (e.g. :mod:`payment_webhook_stripe`) verifies the
  signature on a raw HTTP body and parses the provider-specific JSON
  envelope into a :class:`PaymentEvent`.
* **This module** owns idempotency, the registry mutation, and the
  applied-events ledger. It knows nothing about Stripe / Mercado Pago /
  invoice CSV imports.
* **The API endpoint** is a thin shell that wires the adapter to this
  module and maps typed exceptions to distinct HTTP statuses.

The customer registry mutated here is the same
``rtt_customer_registry_v1`` JSON file ``scripts/customer_lifecycle.py``
already writes manually. The script remains the operator-driven path;
this module is the automated path. They can coexist and are expected to.

Failure policy mirrors the rest of the codebase: every operational error
raises a typed exception so the endpoint returns a distinct status, and
nothing is silently swallowed. There is no "accept everything and log"
path — if a Stripe metadata field is missing, the apply step records the
event as ``rejected`` so the operator can fix the Stripe configuration
and retry.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


WEBHOOK_MODE = "payment_webhook_v1"

# These intentionally mirror the vocabularies in
# ``scripts/customer_lifecycle.py`` and ``scripts/provision_customer_key.py``.
# Keep them in sync if either side adds a plan or status.
VALID_PLANS: frozenset[str] = frozenset({"demo", "starter", "pro", "enterprise"})
VALID_STATUSES: frozenset[str] = frozenset({"active", "suspended", "canceled"})

# Provider-neutral event vocabulary. Provider adapters translate their
# native event types into one of these; unknown native event types map to
# ``ignored`` so the webhook returns 200 (Stripe re-sends only on
# non-2xx) and the ledger records that we saw it.
NEUTRAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "subscription_activated",
        "subscription_updated",
        "subscription_canceled",
        "payment_failed",
        "payment_succeeded",
        "ignored",
    }
)


# ---------------------------------------------------------------------------
# typed exceptions
# ---------------------------------------------------------------------------


class PaymentWebhookError(Exception):
    """Base for all payment-webhook failures."""


class WebhookConfigError(PaymentWebhookError):
    """Webhook secret / registry path missing or malformed.

    Maps to ``503 Service Unavailable`` at the endpoint — the operator
    hasn't enabled the feature, so this is a clear configuration gap,
    not a request-shape problem.
    """


class WebhookSignatureError(PaymentWebhookError):
    """Signature header missing, malformed, expired, or invalid.

    Maps to ``401 Unauthorized``. Distinct from ``400`` so the operator
    can tell "someone hit us without a key" apart from "the body was
    junk".
    """


class WebhookPayloadError(PaymentWebhookError):
    """Provider payload failed parsing or shape validation.

    Maps to ``400 Bad Request``. Stripe's own malformed re-tries would
    land here; we want them visible to the operator.
    """


class EventApplicationError(PaymentWebhookError):
    """Apply step failed for a non-recoverable reason.

    Maps to ``500`` only for genuinely unexpected failures. Domain-level
    rejections (customer not found, missing metadata) are recorded as
    a non-applied :class:`EventApplication` and returned as ``200``.
    """


# ---------------------------------------------------------------------------
# data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentEvent:
    """Provider-neutral webhook event.

    A provider adapter is responsible for filling these fields from its
    native event shape. ``raw`` keeps the original payload so the
    ledger entry preserves enough provenance to audit a dispute later.
    """

    provider: str
    event_id: str
    event_type: str
    customer_id: str
    plan: str | None = None
    status: str | None = None
    payment_reference: str = ""
    monthly_amount: str = ""
    currency: str = ""
    note: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise WebhookPayloadError("PaymentEvent.provider must be non-empty")
        if not self.event_id.strip():
            raise WebhookPayloadError("PaymentEvent.event_id must be non-empty")
        if self.event_type not in NEUTRAL_EVENT_TYPES:
            raise WebhookPayloadError(
                f"PaymentEvent.event_type must be one of "
                f"{sorted(NEUTRAL_EVENT_TYPES)}; got {self.event_type!r}"
            )
        # customer_id is the local registry slug, not the provider's id.
        # An empty slug is OK only for `ignored` events that bypass apply.
        if self.event_type != "ignored" and not self.customer_id.strip():
            raise WebhookPayloadError(
                "PaymentEvent.customer_id is required for non-ignored events"
            )
        if self.plan is not None and self.plan not in VALID_PLANS:
            raise WebhookPayloadError(
                f"PaymentEvent.plan must be one of {sorted(VALID_PLANS)} or None"
            )
        if self.status is not None and self.status not in VALID_STATUSES:
            raise WebhookPayloadError(
                f"PaymentEvent.status must be one of {sorted(VALID_STATUSES)} or None"
            )


@dataclass(frozen=True)
class EventApplication:
    """Result of applying a :class:`PaymentEvent` to the registry.

    Successful apply: ``applied=True`` and ``action`` describes the
    mutation (``status_changed``, ``plan_changed``, ``both_changed``,
    ``no_change``). Non-apply outcomes: ``duplicate`` (event_id seen
    before), ``ignored`` (event_type the engine doesn't act on),
    ``rejected_no_customer`` (no registry row for this customer_id),
    ``rejected_invalid`` (event payload failed apply-time validation).
    Every outcome is recorded in the ledger so reconciliation can see
    rejected events too.
    """

    provider: str
    event_id: str
    event_type: str
    customer_id: str
    applied: bool
    action: str
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None
    reason: str = ""
    applied_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": WEBHOOK_MODE,
            "provider": self.provider,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "customer_id": self.customer_id,
            "applied": self.applied,
            "action": self.action,
            "before": dict(self.before) if self.before is not None else None,
            "after": dict(self.after) if self.after is not None else None,
            "reason": self.reason,
            "applied_at": self.applied_at,
        }


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------


class EventLedger:
    """Append-only record of webhook applications, with idempotency by event_id."""

    def seen(self, event_id: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def record(self, application: EventApplication) -> None:  # pragma: no cover
        raise NotImplementedError


class NullEventLedger(EventLedger):
    """Default ledger: never persists, never deduplicates.

    The webhook still works without a ledger, but every Stripe re-try
    will re-apply the event. In production point ``EBF_PAYMENT_WEBHOOK_LEDGER``
    at a file so retries are idempotent.
    """

    def seen(self, event_id: str) -> bool:
        return False

    def record(self, application: EventApplication) -> None:
        return None


class FileEventLedger(EventLedger):
    """JSONL ledger keyed by ``(provider, event_id)``.

    The first entry for a given key wins; subsequent applications with
    the same key are short-circuited via :meth:`seen`. We scan the file
    on each call rather than caching in memory — webhook traffic is low
    and a stale cache after an out-of-band ledger truncation would be
    worse than a tiny read.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def seen(self, event_id: str) -> bool:
        if not event_id:
            return False
        key = event_id.strip()
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # A truncated tail line shouldn't make us treat the event
                    # as already-seen. Skip and move on; the apply step will
                    # try to write a fresh entry.
                    continue
                if entry.get("event_id") == key:
                    return True
        return False

    def record(self, application: EventApplication) -> None:
        line = json.dumps(application.to_dict(), sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# registry helpers (duplicated from scripts/customer_lifecycle.py on purpose)
# ---------------------------------------------------------------------------


REGISTRY_SCHEMA = "rtt_customer_registry_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_registry(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != REGISTRY_SCHEMA:
        raise EventApplicationError(
            f"unsupported customer registry schema in {path}"
        )
    if not isinstance(data.get("customers"), list):
        raise EventApplicationError(
            f"customer registry {path} must contain a customers list"
        )
    return data


def _save_registry(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    tmp.replace(path)


def _find_customer(data: dict[str, Any], customer_id: str) -> dict[str, Any] | None:
    for item in data.get("customers", []):
        if isinstance(item, dict) and item.get("customer_id") == customer_id:
            return item
    return None


def _append_event(customer: dict[str, Any], event_name: str, note: str) -> None:
    events = customer.setdefault("events", [])
    if not isinstance(events, list):
        # Treat a corrupted events field as a hard apply error rather than
        # blow it away — the operator can fix the registry by hand.
        raise EventApplicationError(
            f"customer {customer.get('customer_id')!r} events field is not a list"
        )
    events.append({"at": _now_iso(), "event": event_name, "note": note.strip()})


def _snapshot(customer: Mapping[str, Any]) -> dict[str, Any]:
    """A small subset of the customer record for ledger before/after."""
    return {
        "customer_id": customer.get("customer_id"),
        "status": customer.get("status"),
        "plan": customer.get("plan"),
        "payment_reference": customer.get("payment_reference", ""),
        "monthly_amount": customer.get("monthly_amount", ""),
        "currency": customer.get("currency", ""),
    }


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def _intended_state(event: PaymentEvent, customer: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(status, plan)`` after applying ``event`` to ``customer``.

    ``None`` means "leave the existing value alone". This is where the
    provider-neutral event types fan back out into concrete registry
    mutations.
    """
    if event.event_type == "subscription_activated":
        return ("active", event.plan)
    if event.event_type == "subscription_updated":
        # status change is optional on updates (Stripe sends one event for
        # both plan and status changes). Only override if the adapter set it.
        return (event.status, event.plan)
    if event.event_type == "subscription_canceled":
        return ("canceled", None)
    if event.event_type == "payment_failed":
        return ("suspended", None)
    if event.event_type == "payment_succeeded":
        # Only re-activate if currently suspended. Don't reset a canceled
        # subscription on a late re-charge — that needs operator review.
        if customer.get("status") == "suspended":
            return ("active", None)
        return (None, None)
    raise EventApplicationError(
        f"no apply mapping for event_type {event.event_type!r}"
    )


def apply_payment_event(
    event: PaymentEvent,
    *,
    registry_path: Path,
    ledger: EventLedger,
) -> EventApplication:
    """Idempotently apply ``event`` to the customer registry.

    Idempotency is keyed on ``event.event_id``: the second call with the
    same id returns an :class:`EventApplication` with ``applied=False``
    and ``action="duplicate"``, no registry mutation, no ledger write.

    The function never raises for domain-level rejections (unknown
    customer, ignored event type) — those become recorded
    :class:`EventApplication` outcomes so the operator can audit them.
    It raises :class:`EventApplicationError` only for I/O or schema
    failures that should propagate as 500.
    """
    if ledger.seen(event.event_id):
        return EventApplication(
            provider=event.provider,
            event_id=event.event_id,
            event_type=event.event_type,
            customer_id=event.customer_id,
            applied=False,
            action="duplicate",
            before=None,
            after=None,
            reason="event_id previously applied",
            applied_at=_now_iso(),
        )

    if event.event_type == "ignored":
        application = EventApplication(
            provider=event.provider,
            event_id=event.event_id,
            event_type=event.event_type,
            customer_id=event.customer_id,
            applied=False,
            action="ignored",
            before=None,
            after=None,
            reason=event.note or "event_type not actioned by this engine",
            applied_at=_now_iso(),
        )
        ledger.record(application)
        return application

    data = _load_registry(registry_path)
    customer = _find_customer(data, event.customer_id)
    if customer is None:
        application = EventApplication(
            provider=event.provider,
            event_id=event.event_id,
            event_type=event.event_type,
            customer_id=event.customer_id,
            applied=False,
            action="rejected_no_customer",
            before=None,
            after=None,
            reason=(
                f"customer_id {event.customer_id!r} not found in registry "
                f"{registry_path}; provision the customer first"
            ),
            applied_at=_now_iso(),
        )
        ledger.record(application)
        return application

    before = _snapshot(customer)
    new_status, new_plan = _intended_state(event, customer)

    changes: list[str] = []
    if new_status is not None and new_status != customer.get("status"):
        customer["status"] = new_status
        changes.append(f"status:{new_status}")
    if new_plan is not None and new_plan != customer.get("plan"):
        customer["plan"] = new_plan
        changes.append(f"plan:{new_plan}")
    # Compare-then-set on metadata fields so a re-sent event whose
    # payload matches the current registry state correctly reports
    # ``no_change`` rather than marking three meaningless mutations.
    if event.payment_reference:
        new_ref = event.payment_reference.strip()
        if new_ref != customer.get("payment_reference", ""):
            customer["payment_reference"] = new_ref
            changes.append("payment_reference")
    if event.monthly_amount:
        new_amount = event.monthly_amount.strip()
        if new_amount != customer.get("monthly_amount", ""):
            customer["monthly_amount"] = new_amount
            changes.append("monthly_amount")
    if event.currency:
        new_currency = event.currency.strip().upper()
        if new_currency != customer.get("currency", ""):
            customer["currency"] = new_currency
            changes.append("currency")

    customer["updated_at"] = _now_iso()
    _append_event(
        customer,
        ",".join(changes) if changes else f"webhook:{event.event_type}",
        event.note or f"{event.provider} event {event.event_id}",
    )

    action = (
        "no_change"
        if not changes
        else "both_changed"
        if any(c.startswith("status:") for c in changes)
        and any(c.startswith("plan:") for c in changes)
        else "status_changed"
        if any(c.startswith("status:") for c in changes)
        else "plan_changed"
        if any(c.startswith("plan:") for c in changes)
        else "metadata_only"
    )

    _save_registry(registry_path, data)
    after = _snapshot(customer)

    application = EventApplication(
        provider=event.provider,
        event_id=event.event_id,
        event_type=event.event_type,
        customer_id=event.customer_id,
        applied=bool(changes),
        action=action,
        before=before,
        after=after,
        reason=", ".join(changes) if changes else "registry already at target state",
        applied_at=_now_iso(),
    )
    ledger.record(application)
    return application


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentWebhookConfig:
    """Resolved configuration for the payment webhook endpoint.

    Either the Stripe secret or the registry path being unset means the
    endpoint is disabled and will return 503. Both must be present to
    enable the feature.
    """

    enabled: bool
    stripe_secret: str | None
    registry_path: Path | None
    ledger_path: Path | None
    signature_tolerance_seconds: int

    def require_enabled(self) -> None:
        if not self.enabled:
            raise WebhookConfigError(
                "payment webhook not configured; set "
                "EBF_STRIPE_WEBHOOK_SECRET and EBF_CUSTOMER_REGISTRY to enable"
            )


def load_payment_webhook_config(
    env: Mapping[str, str] | None = None,
) -> PaymentWebhookConfig:
    source = dict(os.environ if env is None else env)
    stripe_secret = (source.get("EBF_STRIPE_WEBHOOK_SECRET") or "").strip() or None
    registry_raw = (source.get("EBF_CUSTOMER_REGISTRY") or "").strip()
    registry_path = Path(registry_raw) if registry_raw else None
    ledger_raw = (source.get("EBF_PAYMENT_WEBHOOK_LEDGER") or "").strip()
    ledger_path = Path(ledger_raw) if ledger_raw else None

    tolerance_raw = (source.get("EBF_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS") or "").strip()
    if tolerance_raw:
        try:
            tolerance = int(tolerance_raw)
        except ValueError as exc:
            raise WebhookConfigError(
                "EBF_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS must be a positive integer"
            ) from exc
        if tolerance < 1:
            raise WebhookConfigError(
                "EBF_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS must be positive"
            )
    else:
        # Stripe's recommended default.
        tolerance = 300

    enabled = stripe_secret is not None and registry_path is not None
    return PaymentWebhookConfig(
        enabled=enabled,
        stripe_secret=stripe_secret,
        registry_path=registry_path,
        ledger_path=ledger_path,
        signature_tolerance_seconds=tolerance,
    )


def get_ledger(config: PaymentWebhookConfig) -> EventLedger:
    if config.ledger_path is None:
        return NullEventLedger()
    return FileEventLedger(config.ledger_path)


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def fingerprint_event_id(event_id: str) -> str:
    """Short stable hash of an event id, for log lines that should not echo
    the full provider id verbatim."""
    return hashlib.blake2b(event_id.encode("utf-8"), digest_size=6).hexdigest()


__all__ = [
    "WEBHOOK_MODE",
    "VALID_PLANS",
    "VALID_STATUSES",
    "NEUTRAL_EVENT_TYPES",
    "PaymentWebhookError",
    "WebhookConfigError",
    "WebhookSignatureError",
    "WebhookPayloadError",
    "EventApplicationError",
    "PaymentEvent",
    "EventApplication",
    "EventLedger",
    "NullEventLedger",
    "FileEventLedger",
    "PaymentWebhookConfig",
    "apply_payment_event",
    "load_payment_webhook_config",
    "get_ledger",
    "fingerprint_event_id",
]
# Silence the unused-imports linter on intentional re-exports.
_ = asdict
