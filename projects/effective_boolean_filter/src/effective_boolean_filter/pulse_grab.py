"""Execution-hold security primitive.

Pulse Grab keeps a proposed action available, but holds execution until the
required controls are present. It is for operational actions, not truth
evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from .trace_gate import stable_evidence_hash


PULSE_GRAB_MODE = "pulse_grab_v0"

PulseGrabStatus = Literal["allow", "hold"]
PulseGrabRisk = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class PulseGrabDecision:
    mode: str
    status: PulseGrabStatus
    action_id: str
    risk_level: PulseGrabRisk
    reasons: tuple[str, ...]
    required_controls: tuple[str, ...]
    supplied_controls: tuple[str, ...]
    missing_controls: tuple[str, ...]
    evidence_hash: str

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "action_id": self.action_id,
            "risk_level": self.risk_level,
            "reasons": list(self.reasons),
            "required_controls": list(self.required_controls),
            "supplied_controls": list(self.supplied_controls),
            "missing_controls": list(self.missing_controls),
        }

    def to_dict(self) -> dict[str, Any]:
        out = self.payload()
        out["evidence_hash"] = self.evidence_hash
        return out


def evaluate_pulse_grab(
    *,
    action_id: str,
    irreversible: bool = False,
    touches_secrets: bool = False,
    touches_customer_content: bool = False,
    moves_money: bool = False,
    changes_legal_terms: bool = False,
    external_publication: bool = False,
    supplied_controls: Sequence[str] = (),
) -> PulseGrabDecision:
    """Return an execution decision for an operational action.

    The action is not discarded when controls are missing. It remains holdable
    with a precise list of missing controls.
    """
    normalized_controls = tuple(sorted({control.strip() for control in supplied_controls if control.strip()}))
    reasons: list[str] = []
    required_controls: list[str] = []

    if irreversible:
        reasons.append("irreversible_action")
        required_controls.append("operator_approval")
    if touches_secrets:
        reasons.append("secret_custody")
        required_controls.append("secret_vault_change_review")
    if touches_customer_content:
        reasons.append("customer_content_access")
        required_controls.append("customer_data_need_to_know")
    if moves_money:
        reasons.append("money_movement")
        required_controls.extend(["finance_approval", "payment_reference"])
    if changes_legal_terms:
        reasons.append("legal_terms_change")
        required_controls.append("counsel_review")
    if external_publication:
        reasons.append("external_publication")
        required_controls.append("operator_approval")

    deduped_required = tuple(sorted(set(required_controls)))
    missing = tuple(
        control for control in deduped_required if control not in normalized_controls
    )
    status: PulseGrabStatus = "hold" if missing else "allow"
    risk_level = _risk_level(
        irreversible=irreversible,
        touches_secrets=touches_secrets,
        touches_customer_content=touches_customer_content,
        moves_money=moves_money,
        changes_legal_terms=changes_legal_terms,
        external_publication=external_publication,
    )
    payload = {
        "mode": PULSE_GRAB_MODE,
        "status": status,
        "action_id": action_id,
        "risk_level": risk_level,
        "reasons": list(reasons),
        "required_controls": list(deduped_required),
        "supplied_controls": list(normalized_controls),
        "missing_controls": list(missing),
    }
    return PulseGrabDecision(
        mode=PULSE_GRAB_MODE,
        status=status,
        action_id=action_id,
        risk_level=risk_level,
        reasons=tuple(reasons),
        required_controls=deduped_required,
        supplied_controls=normalized_controls,
        missing_controls=missing,
        evidence_hash=stable_evidence_hash(payload),
    )


def verify_pulse_grab_decision(decision: PulseGrabDecision | None) -> bool:
    if decision is None:
        return False
    return decision.evidence_hash == stable_evidence_hash(decision.payload())


def _risk_level(
    *,
    irreversible: bool,
    touches_secrets: bool,
    touches_customer_content: bool,
    moves_money: bool,
    changes_legal_terms: bool,
    external_publication: bool,
) -> PulseGrabRisk:
    high_risk = (
        irreversible,
        touches_secrets,
        touches_customer_content,
        moves_money,
        changes_legal_terms,
    )
    if any(high_risk):
        return "high"
    if external_publication:
        return "medium"
    return "low"
