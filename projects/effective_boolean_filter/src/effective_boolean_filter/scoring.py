"""Effectiveness / bogusness scoring (spec Section 9).

The score is a weighted sum over an explicit ScoreVector. Every penalty
records a reason on the vector so the report layer can show *why* a
field is below 1.0.
"""
from __future__ import annotations

from .schemas import (
    ClaimNode,
    ContradictionReport,
    Issue,
    Probe,
    Recommendation,
    ScoreVector,
    Strictness,
)


WEIGHTS = {
    "negation_consistency": 0.20,
    "scope_preservation": 0.15,
    "definition_stability": 0.15,
    "context_fit": 0.15,
    "contradiction_containment": 0.10,
    "reactive_performance": 0.15,
    "testability": 0.10,
}


CONTRADICTION_PENALTY: dict[str, float] = {
    "none": 0.0,
    "scope_resolved": 0.10,
    "temporal_resolved": 0.10,
    "definition_resolved": 0.15,
    "contained": 0.20,
    "conclusion_dependent": 0.60,
    "breaking": 0.85,
}


STRICTNESS_MULT: dict[Strictness, float] = {
    "low": 0.7,
    "medium": 1.0,
    "high": 1.3,
}


def _penalise(vector: ScoreVector, field: str, amount: float, reason: str) -> None:
    cur = getattr(vector, field)
    new = max(0.0, cur - amount)
    setattr(vector, field, new)
    vector.add_reason(field, f"-{amount:.2f}: {reason}")


def score_argument(
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
    issues: list[Issue],
    contradiction: ContradictionReport,
    probes: list[Probe],
    strictness: Strictness = "medium",
) -> tuple[ScoreVector, float, float]:
    v = ScoreVector()
    mult = STRICTNESS_MULT[strictness]

    for issue in issues:
        code = issue.code
        if code == "untracked_shift":
            _penalise(v, "negation_consistency", 0.45 * mult, issue.message)
        elif code == "epistemic_to_ontological_shift":
            _penalise(v, "negation_consistency", 0.50 * mult, issue.message)
            _penalise(v, "reactive_performance", 0.20 * mult, "depends on absence of disproof")
        elif code in ("simulation_to_production_shift", "legal_to_physical_shift",
                      "possibility_to_actuality_shift"):
            _penalise(v, "scope_preservation", 0.50 * mult, issue.message)
            _penalise(v, "context_fit", 0.20 * mult, "scope jump misaligns conclusion with premises")
        elif code == "definition_shift":
            _penalise(v, "definition_stability", 0.50 * mult, issue.message)
        elif code == "unsupported_strengthening":
            _penalise(v, "context_fit", 0.30 * mult, issue.message)
            _penalise(v, "testability", 0.15 * mult, "claim is stronger than evidence")
        elif code.startswith("contradiction_"):
            status = code.removeprefix("contradiction_")
            penalty = CONTRADICTION_PENALTY.get(status, 0.20)
            _penalise(v, "contradiction_containment", penalty * mult, issue.message)

    # contradiction state (overrides if worse than per-issue penalties)
    cont_penalty = CONTRADICTION_PENALTY.get(contradiction.status, 0.0)
    if cont_penalty > (1.0 - v.contradiction_containment):
        v.contradiction_containment = max(0.0, 1.0 - cont_penalty * mult)
        v.add_reason("contradiction_containment", f"status={contradiction.status} (override)")

    # Reactive performance: assume probes are unanswered initially -> mid score.
    # If probes have been answered, compute pass rate.
    answered = [p for p in probes if p.passed is not None]
    if answered:
        rate = sum(1 for p in answered if p.passed) / len(answered)
        v.reactive_performance = rate
        v.add_reason("reactive_performance", f"{len(answered)} probe(s) answered, pass rate {rate:.2f}")
    else:
        v.reactive_performance = min(v.reactive_performance, 0.5)
        v.add_reason("reactive_performance", "no probes answered yet")

    # If the structural verdict is an untracked shift, the argument cannot
    # plausibly survive its own probes — clamp reactive_performance and
    # testability hard.
    error_codes = {i.code for i in issues if i.severity == "error"}
    if {"untracked_shift", "epistemic_to_ontological_shift"} & error_codes:
        v.reactive_performance = min(v.reactive_performance, 0.15)
        v.add_reason("reactive_performance", "untracked structural shift makes probes unreliable")
        v.testability = min(v.testability, 0.25)
        v.add_reason("testability", "shift hides what would falsify the claim")

    # Testability: heuristic from probe coverage and issues
    if any("ask_falsifier" == p.type for p in probes):
        v.testability = max(v.testability, 0.5)
    if conclusion is not None and conclusion.negation_type == "epistemic":
        _penalise(v, "testability", 0.15 * mult, "conclusion is itself epistemic absence")
    v.add_reason("testability", "baseline 0.5; raised when falsifier probe applies")

    # Implementation relevance: bumps if claim mentions implementation/practice
    impl_text = (
        ((conclusion.text if conclusion else "")
         + " "
         + " ".join(p.text for p in premises)).lower()
    )
    if any(k in impl_text for k in ("deploy", "production", "implementation", "in practice")):
        v.implementation_relevance = 0.7
        v.add_reason("implementation_relevance", "premise/conclusion references practice")

    overall = sum(WEIGHTS[k] * getattr(v, k) for k in WEIGHTS)
    bogusness = 1.0 - overall
    return v, round(overall, 3), round(bogusness, 3)


def recommend(
    polarity: str,
    effectiveness: float,
    contradiction: ContradictionReport,
    issues: list[Issue],
) -> Recommendation:
    error_codes = {i.code for i in issues if i.severity == "error"}
    if contradiction.status == "breaking":
        return "reject"
    if "epistemic_to_ontological_shift" in error_codes and polarity == "untracked_shift":
        return "reject"
    if effectiveness < 0.30:
        return "reject"
    if effectiveness < 0.55 or polarity in ("untracked_shift", "unstable"):
        return "needs_testing"
    if effectiveness < 0.75 or contradiction.status not in ("none", "scope_resolved", "temporal_resolved"):
        return "accept_with_caveats"
    return "accept"
