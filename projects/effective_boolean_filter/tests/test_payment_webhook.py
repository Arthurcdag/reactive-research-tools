"""Unit tests for the provider-neutral payment webhook engine.

These exercise the dedupe ledger, registry mutation, status/plan
transitions, and configuration loading. Stripe-specific signature and
parsing logic is covered separately in
``test_payment_webhook_stripe.py``; the endpoint surface is covered in
``test_api_payment_webhook.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.effective_boolean_filter.payment_webhook import (
    EventApplicationError,
    FileEventLedger,
    NullEventLedger,
    PaymentEvent,
    PaymentWebhookConfig,
    WebhookConfigError,
    WebhookPayloadError,
    apply_payment_event,
    fingerprint_event_id,
    get_ledger,
    load_payment_webhook_config,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_registry(path: Path, **overrides) -> None:
    record = {
        "customer_id": "customer-a",
        "plan": "starter",
        "status": "active",
        "key_fingerprint": "abc123",
        "payment_reference": "INV-2026-001",
        "monthly_amount": "29.00",
        "currency": "USD",
    }
    record.update(overrides)
    payload = {"schema": "rtt_customer_registry_v1", "customers": [record]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _event(**overrides) -> PaymentEvent:
    defaults = dict(
        provider="stripe",
        event_id="evt_001",
        event_type="subscription_updated",
        customer_id="customer-a",
        plan="pro",
        status=None,
        payment_reference="stripe:sub_abc",
        monthly_amount="79.00",
        currency="USD",
        note="stripe.customer.subscription.updated",
        raw={"id": "evt_001"},
    )
    defaults.update(overrides)
    return PaymentEvent(**defaults)


# ---------------------------------------------------------------------------
# PaymentEvent validation
# ---------------------------------------------------------------------------


def test_payment_event_rejects_unknown_event_type():
    with pytest.raises(WebhookPayloadError, match="event_type"):
        _event(event_type="not_a_real_event")


def test_payment_event_rejects_blank_event_id():
    with pytest.raises(WebhookPayloadError, match="event_id"):
        _event(event_id="   ")


def test_payment_event_rejects_blank_customer_id_for_non_ignored():
    with pytest.raises(WebhookPayloadError, match="customer_id"):
        _event(customer_id="")


def test_payment_event_allows_blank_customer_id_for_ignored():
    # Ignored events legitimately have no customer because Stripe sends
    # many envelope-only event types we don't act on.
    event = _event(
        event_type="ignored", customer_id="", plan=None, status=None
    )
    assert event.event_type == "ignored"


def test_payment_event_rejects_unknown_plan():
    with pytest.raises(WebhookPayloadError, match="plan"):
        _event(plan="ultra-mega")


def test_payment_event_rejects_unknown_status():
    with pytest.raises(WebhookPayloadError, match="status"):
        _event(event_type="subscription_updated", status="active-ish")


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------


def test_null_ledger_never_dedupes():
    ledger = NullEventLedger()
    assert ledger.seen("anything") is False
    # record is a no-op but must accept the call
    ledger.record(_application())
    assert ledger.seen("anything") is False


def test_file_ledger_dedupes_after_record(tmp_path: Path):
    ledger = FileEventLedger(tmp_path / "ledger.jsonl")
    application = _application(event_id="evt_dedupe")
    assert ledger.seen("evt_dedupe") is False
    ledger.record(application)
    assert ledger.seen("evt_dedupe") is True
    # other ids stay unseen
    assert ledger.seen("evt_other") is False


def test_file_ledger_survives_corrupted_tail(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = FileEventLedger(path)
    ledger.record(_application(event_id="evt_good"))
    # operator pastes garbage into the file by accident
    with path.open("a", encoding="utf-8") as f:
        f.write("not-json-at-all\n")
    # we still see the good entry and don't crash
    assert ledger.seen("evt_good") is True
    assert ledger.seen("evt_missing") is False


def _application(event_id: str = "evt_001"):
    """Helper application for ledger tests; mirrors what apply produces."""
    from src.effective_boolean_filter.payment_webhook import EventApplication

    return EventApplication(
        provider="stripe",
        event_id=event_id,
        event_type="subscription_updated",
        customer_id="customer-a",
        applied=True,
        action="plan_changed",
        before={"plan": "starter"},
        after={"plan": "pro"},
        reason="plan:pro",
        applied_at="2026-05-15T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# apply_payment_event
# ---------------------------------------------------------------------------


def test_apply_subscription_activated_sets_active_and_plan(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry, status="canceled", plan="demo")
    ledger = FileEventLedger(tmp_path / "ledger.jsonl")
    event = _event(event_type="subscription_activated", plan="pro")

    result = apply_payment_event(event, registry_path=registry, ledger=ledger)

    assert result.applied is True
    assert result.action == "both_changed"
    data = json.loads(registry.read_text())
    customer = data["customers"][0]
    assert customer["status"] == "active"
    assert customer["plan"] == "pro"
    # event appended for audit
    assert customer["events"][-1]["event"].startswith("status:active")


def test_apply_subscription_updated_changes_plan_only(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry, plan="starter")
    ledger = FileEventLedger(tmp_path / "ledger.jsonl")
    event = _event(event_type="subscription_updated", plan="pro", status=None)

    result = apply_payment_event(event, registry_path=registry, ledger=ledger)

    assert result.applied is True
    assert result.action == "plan_changed"
    assert result.before["plan"] == "starter"
    assert result.after["plan"] == "pro"


def test_apply_subscription_canceled_marks_canceled(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry)
    ledger = NullEventLedger()
    event = _event(event_type="subscription_canceled", plan=None)

    result = apply_payment_event(event, registry_path=registry, ledger=ledger)

    assert result.applied is True
    customer = json.loads(registry.read_text())["customers"][0]
    assert customer["status"] == "canceled"


def test_apply_payment_failed_suspends(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry, status="active")
    event = _event(event_type="payment_failed", plan=None)

    result = apply_payment_event(
        event, registry_path=registry, ledger=NullEventLedger()
    )

    assert result.applied is True
    assert result.action == "status_changed"
    customer = json.loads(registry.read_text())["customers"][0]
    assert customer["status"] == "suspended"


def test_apply_payment_succeeded_only_revives_suspended(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry, status="suspended")
    event = _event(event_type="payment_succeeded", plan=None)
    result = apply_payment_event(
        event, registry_path=registry, ledger=NullEventLedger()
    )
    assert result.applied is True
    assert json.loads(registry.read_text())["customers"][0]["status"] == "active"

    # Run again on a canceled subscription — must NOT re-activate.
    # Seed payment metadata identical to the event so we test the
    # status-revival path in isolation, not metadata drift.
    _seed_registry(
        registry,
        status="canceled",
        payment_reference="stripe:sub_abc",
        monthly_amount="79.00",
        currency="USD",
    )
    other = _event(event_id="evt_002", event_type="payment_succeeded", plan=None)
    result = apply_payment_event(
        other, registry_path=registry, ledger=NullEventLedger()
    )
    assert result.applied is False
    assert result.action == "no_change"
    assert json.loads(registry.read_text())["customers"][0]["status"] == "canceled"


def test_apply_idempotent_via_ledger(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry, plan="starter")
    ledger = FileEventLedger(tmp_path / "ledger.jsonl")
    event = _event(event_type="subscription_updated", plan="pro")

    first = apply_payment_event(event, registry_path=registry, ledger=ledger)
    second = apply_payment_event(event, registry_path=registry, ledger=ledger)

    assert first.applied is True
    assert second.applied is False
    assert second.action == "duplicate"
    # registry was not mutated a second time — still pro, not e.g. demo
    assert json.loads(registry.read_text())["customers"][0]["plan"] == "pro"


def test_apply_rejects_unknown_customer(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry)
    event = _event(customer_id="customer-ghost", plan="pro")

    result = apply_payment_event(
        event, registry_path=registry, ledger=NullEventLedger()
    )

    assert result.applied is False
    assert result.action == "rejected_no_customer"
    assert "customer-ghost" in result.reason


def test_apply_ignored_records_but_does_not_load_registry(tmp_path: Path):
    # Registry file does not exist on disk: ignored events must not
    # touch it, so the apply succeeds even when the registry is absent.
    registry = tmp_path / "registry.json"
    assert not registry.exists()
    event = _event(
        event_id="evt_ignored",
        event_type="ignored",
        customer_id="",
        plan=None,
        status=None,
    )
    result = apply_payment_event(
        event, registry_path=registry, ledger=NullEventLedger()
    )
    assert result.applied is False
    assert result.action == "ignored"
    assert not registry.exists()


def test_apply_no_change_when_already_at_target_state(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry, plan="pro", status="active")
    # Mirror the seed's metadata so the apply path can recognise
    # "nothing actually changed". This is the realistic shape of a
    # Stripe re-send after the operator manually applied the same plan.
    event = _event(
        event_type="subscription_updated",
        plan="pro",
        status="active",
        payment_reference="INV-2026-001",
        monthly_amount="29.00",
        currency="USD",
    )
    result = apply_payment_event(
        event, registry_path=registry, ledger=NullEventLedger()
    )
    assert result.applied is False
    assert result.action == "no_change"


def test_apply_writes_payment_reference_amount_currency(tmp_path: Path):
    registry = tmp_path / "registry.json"
    _seed_registry(registry)
    event = _event(
        event_type="subscription_updated",
        plan="pro",
        payment_reference="stripe:sub_xyz",
        monthly_amount="79.00",
        currency="brl",
    )
    apply_payment_event(event, registry_path=registry, ledger=NullEventLedger())
    customer = json.loads(registry.read_text())["customers"][0]
    assert customer["payment_reference"] == "stripe:sub_xyz"
    assert customer["monthly_amount"] == "79.00"
    assert customer["currency"] == "BRL"  # normalized to upper


def test_apply_raises_on_corrupted_registry_schema(tmp_path: Path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema": "wrong"}))
    event = _event()
    with pytest.raises(EventApplicationError, match="schema"):
        apply_payment_event(
            event, registry_path=registry, ledger=NullEventLedger()
        )


def test_apply_raises_when_customer_events_field_corrupted(tmp_path: Path):
    registry = tmp_path / "registry.json"
    payload = {
        "schema": "rtt_customer_registry_v1",
        "customers": [
            {
                "customer_id": "customer-a",
                "plan": "starter",
                "status": "active",
                "events": "should-be-a-list",
            }
        ],
    }
    registry.write_text(json.dumps(payload))
    event = _event(event_type="subscription_updated", plan="pro")
    with pytest.raises(EventApplicationError, match="events"):
        apply_payment_event(
            event, registry_path=registry, ledger=NullEventLedger()
        )


# ---------------------------------------------------------------------------
# config loading
# ---------------------------------------------------------------------------


def test_load_config_defaults_disabled():
    config = load_payment_webhook_config({})
    assert config.enabled is False
    assert config.stripe_secret is None
    assert config.registry_path is None
    assert config.ledger_path is None
    assert config.signature_tolerance_seconds == 300


def test_load_config_enabled_when_secret_and_registry_present(tmp_path: Path):
    config = load_payment_webhook_config(
        {
            "EBF_STRIPE_WEBHOOK_SECRET": "whsec_test",
            "EBF_CUSTOMER_REGISTRY": str(tmp_path / "registry.json"),
            "EBF_PAYMENT_WEBHOOK_LEDGER": str(tmp_path / "ledger.jsonl"),
            "EBF_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS": "60",
        }
    )
    assert config.enabled is True
    assert config.stripe_secret == "whsec_test"
    assert config.signature_tolerance_seconds == 60


def test_load_config_requires_both_secret_and_registry(tmp_path: Path):
    only_secret = load_payment_webhook_config(
        {"EBF_STRIPE_WEBHOOK_SECRET": "whsec_test"}
    )
    assert only_secret.enabled is False
    only_registry = load_payment_webhook_config(
        {"EBF_CUSTOMER_REGISTRY": str(tmp_path / "r.json")}
    )
    assert only_registry.enabled is False


def test_load_config_rejects_invalid_tolerance():
    with pytest.raises(WebhookConfigError):
        load_payment_webhook_config(
            {"EBF_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS": "abc"}
        )
    with pytest.raises(WebhookConfigError):
        load_payment_webhook_config(
            {"EBF_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS": "0"}
        )


def test_get_ledger_returns_file_or_null(tmp_path: Path):
    enabled = PaymentWebhookConfig(
        enabled=True,
        stripe_secret="x",
        registry_path=tmp_path / "r.json",
        ledger_path=tmp_path / "ledger.jsonl",
        signature_tolerance_seconds=300,
    )
    assert isinstance(get_ledger(enabled), FileEventLedger)
    disabled_ledger = PaymentWebhookConfig(
        enabled=True,
        stripe_secret="x",
        registry_path=tmp_path / "r.json",
        ledger_path=None,
        signature_tolerance_seconds=300,
    )
    assert isinstance(get_ledger(disabled_ledger), NullEventLedger)


def test_fingerprint_event_id_is_short_and_stable():
    fp1 = fingerprint_event_id("evt_abc")
    fp2 = fingerprint_event_id("evt_abc")
    fp3 = fingerprint_event_id("evt_other")
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 12  # 6-byte blake2b digest hex
