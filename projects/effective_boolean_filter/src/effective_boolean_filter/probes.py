"""Reactive probe generator (spec Section 8).

Probes are deterministic templates parameterised by detected weaknesses.
The LLM layer (when added later) can paraphrase them or supply answers,
but the deterministic engine owns *which* probe types fire and why.
"""
from __future__ import annotations

from .schemas import ClaimNode, Issue, Probe


def _probe(
    type_: str,
    question: str,
    purpose: str,
    failure: str,
    target: str | None = None,
) -> Probe:
    return Probe(
        type=type_,
        question=question,
        purpose=purpose,
        expected_failure_mode=failure,
        targets_node_id=target,
    )


def _has_issue(issues: list[Issue], code_substr: str) -> bool:
    return any(code_substr in i.code for i in issues)


def generate_probes(
    claim: str,
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
    issues: list[Issue],
) -> list[Probe]:
    probes: list[Probe] = []

    # Always-on probes (Section 8.1 baseline)
    probes.append(_probe(
        "ask_falsifier",
        "What concrete observation or experiment would falsify the claim?",
        "testability",
        "missing falsifier",
        target=conclusion.id if conclusion else None,
    ))
    probes.append(_probe(
        "ask_prediction",
        "What measurable prediction does the claim make?",
        "reactive performance",
        "no measurable consequences",
        target=conclusion.id if conclusion else None,
    ))
    probes.append(_probe(
        "ask_implementation",
        f"What concrete implementation or decision would change if the claim were false: {claim!r}?",
        "implementation relevance",
        "no implementation impact",
        target=conclusion.id if conclusion else None,
    ))

    # Issue-targeted probes
    if _has_issue(issues, "epistemic_to_ontological"):
        probes.append(_probe(
            "remove_premise",
            "Does the conclusion still follow if the absence-of-disproof premise is removed?",
            "epistemic dependency check",
            "argument depends on absence-of-disproof",
        ))
        probes.append(_probe(
            "ask_dependency",
            "Which premise carries the proof burden, given that absence of disproof is not proof?",
            "burden of proof",
            "burden never assigned",
        ))

    if _has_issue(issues, "scope_shift") or _has_issue(issues, "simulation_to_production"):
        probes.append(_probe(
            "weaken_premise",
            "Does the conclusion preserve the same scope as the premise (e.g. simulation vs production)?",
            "scope preservation",
            "scope jump",
        ))
        probes.append(_probe(
            "ask_implementation",
            "Has the simulation/theoretical result been validated in the target deployment context?",
            "scope bridge check",
            "no validation bridge",
        ))

    if _has_issue(issues, "legal_to_physical"):
        probes.append(_probe(
            "swap_definition",
            "Does 'possible' here mean legally permitted or physically realisable?",
            "definition equivocation",
            "modal equivocation",
        ))

    if _has_issue(issues, "definition_shift"):
        probes.append(_probe(
            "swap_definition",
            "Is each key term used with the same definition throughout the argument?",
            "definition stability",
            "equivocation",
        ))

    if _has_issue(issues, "unsupported_strengthening"):
        probes.append(_probe(
            "weaken_premise",
            "If the strongest premise were weakened, would the conclusion still hold?",
            "strength match",
            "conclusion exceeds premises",
        ))

    if _has_issue(issues, "untracked_shift"):
        probes.append(_probe(
            "invert_premise",
            "If the underlying object/scope/definition shift were inverted, does the conclusion change?",
            "polarity dependency",
            "hidden polarity dependence",
        ))

    if _has_issue(issues, "contradiction"):
        probes.append(_probe(
            "ask_dependency",
            "Does the conclusion depend on the contradictory premises, or only on the consistent subset?",
            "contradiction containment",
            "conclusion uses contradictory premises",
        ))

    # Universal-claim brittleness
    text = " " + claim.lower() + " "
    if any(w in text for w in (" all ", " every ", " always ", " never ", " any ", " no ")):
        probes.append(_probe(
            "ask_counterexample",
            "Can a single counterexample to the universal claim be constructed?",
            "universal claim brittleness",
            "counterexample exists",
        ))

    # Convert rhetoric into measurement
    probes.append(_probe(
        "ask_measurable_effect",
        f"What is the measurable, task-level effect of accepting the claim: {claim!r}?",
        "task-level effectiveness",
        "no task-level metric",
        target=conclusion.id if conclusion else None,
    ))

    # Cap at 8 to keep reports actionable
    return probes[:8]
