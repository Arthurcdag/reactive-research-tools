from __future__ import annotations

from dataclasses import replace

from src.effective_boolean_filter.pulse_grab import (
    evaluate_pulse_grab,
    verify_pulse_grab_decision,
)


def test_pulse_grab_allows_low_risk_action():
    decision = evaluate_pulse_grab(action_id="refresh-dashboard")
    assert decision.status == "allow"
    assert decision.risk_level == "low"
    assert decision.required_controls == ()
    assert verify_pulse_grab_decision(decision) is True


def test_pulse_grab_holds_money_and_legal_action_until_controls_exist():
    decision = evaluate_pulse_grab(
        action_id="change-paid-contract",
        moves_money=True,
        changes_legal_terms=True,
        supplied_controls=("finance_approval",),
    )
    assert decision.status == "hold"
    assert decision.risk_level == "high"
    assert decision.reasons == ("money_movement", "legal_terms_change")
    assert decision.missing_controls == ("counsel_review", "payment_reference")


def test_pulse_grab_allows_high_risk_action_when_controls_exist():
    decision = evaluate_pulse_grab(
        action_id="rotate-customer-secret",
        touches_secrets=True,
        supplied_controls=("secret_vault_change_review",),
    )
    assert decision.status == "allow"
    assert decision.required_controls == ("secret_vault_change_review",)


def test_pulse_grab_receipt_detects_mutation():
    decision = evaluate_pulse_grab(
        action_id="publish-pricing",
        external_publication=True,
        supplied_controls=("operator_approval",),
    )
    bad = replace(decision, status="hold")
    assert verify_pulse_grab_decision(decision) is True
    assert verify_pulse_grab_decision(bad) is False
