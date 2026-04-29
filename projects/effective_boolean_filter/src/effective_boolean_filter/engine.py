"""Top-level orchestration.

Pipeline (spec Section 10):

    raw argument
      -> parser extracts candidate claims (advisory)
      -> deterministic polarity engine (authoritative trace)
      -> scope tracker
      -> definition tracker
      -> contradiction module (no explosion)
      -> probe generator (advisory + templates)
      -> scoring engine (authoritative report)
"""
from __future__ import annotations

from .contradiction import detect_contradictions
from .definitions import detect_definition_shifts
from .parser import parse_argument, parse_claim
from .polarity import evaluate_polarity
from .probes import generate_probes
from .schemas import (
    ArgumentInput,
    ClaimNode,
    EvaluationReport,
    Issue,
    Polarity,
    Probe,
    ScoreVector,
    Strictness,
)
from .scope import detect_scope_shifts, detect_unsupported_strengthening
from .scoring import recommend, score_argument


def evaluate_argument(
    claim: str,
    argument: str,
    context: str = "",
    task: str = "argument evaluation",
    strictness: Strictness = "medium",
) -> EvaluationReport:
    inp = ArgumentInput(
        claim=claim, argument=argument, context=context, task=task, strictness=strictness
    )

    # Parse: claim becomes a top-level node; argument is split into premises + conclusion.
    claim_node = parse_claim(claim, context_id=context or "default")
    parsed = parse_argument(argument, context_id=context or "default")
    premises = parsed.premises
    conclusion = parsed.conclusion or claim_node

    # If neither argument nor claim provides a conclusion, treat the claim as one.
    if parsed.conclusion is None:
        conclusion = ClaimNode(**{**claim_node.__dict__, "is_premise": False, "is_conclusion": True})

    # 1. polarity / negation parity
    verdict = evaluate_polarity(premises, conclusion)

    # 2. scope shifts + unsupported strengthening
    scope_steps, scope_issues = detect_scope_shifts(premises, conclusion)
    strengthening_issues = detect_unsupported_strengthening(premises, conclusion)

    # 3. definition shifts (mutates definition_id on nodes)
    definition_issues = detect_definition_shifts(premises + [conclusion])

    # 4. contradictions
    contradiction_report, contradiction_issues = detect_contradictions(premises, conclusion)

    issues: list[Issue] = (
        list(verdict.issues)
        + scope_issues
        + strengthening_issues
        + definition_issues
        + contradiction_issues
    )

    # 5. probes
    probes: list[Probe] = generate_probes(claim, premises, conclusion, issues)

    # 6. score
    score_vector, effectiveness, bogusness = score_argument(
        premises, conclusion, issues, contradiction_report, probes, strictness
    )

    # 7. final polarity decision
    polarity = _decide_polarity(verdict.polarity, issues, contradiction_report)

    # If the structural verdict is untracked_shift or contradiction, the
    # argument is fundamentally compromised — clamp effectiveness so the
    # numeric score reflects the structural verdict.
    if polarity in ("untracked_shift", "contradiction"):
        effectiveness = min(effectiveness, 0.40)
        bogusness = round(1.0 - effectiveness, 3)
        score_vector.add_reason(
            "negation_consistency",
            f"effectiveness clamped to {effectiveness:.2f} due to {polarity}",
        )

    rec = recommend(polarity, effectiveness, contradiction_report, issues)
    confidence = _confidence(premises, conclusion, issues)

    return EvaluationReport(
        effective_polarity=polarity,
        effectiveness_score=effectiveness,
        bogusness_score=bogusness,
        score_vector=score_vector,
        claims=[claim_node, *premises, conclusion]
        if conclusion is not claim_node
        else [claim_node, *premises],
        trace=verdict.transformation_steps + scope_steps,
        issues=issues,
        probes=probes,
        contradiction=contradiction_report,
        recommendation=rec,
        confidence=confidence,
        input=inp,
    )


def _decide_polarity(
    base: Polarity,
    issues: list[Issue],
    contradiction,
) -> Polarity:
    error_codes = {i.code for i in issues if i.severity == "error"}
    if contradiction.status == "breaking":
        return "contradiction"
    if "untracked_shift" in error_codes:
        return "untracked_shift"
    if "epistemic_to_ontological_shift" in error_codes:
        return "untracked_shift"
    if any(c.endswith("_shift") for c in error_codes):
        return "unstable"
    if "unsupported_strengthening" in error_codes:
        return "unstable"
    if contradiction.status in ("conclusion_dependent",):
        return "unstable"
    return base


def _confidence(
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
    issues: list[Issue],
) -> float:
    nodes = list(premises) + ([conclusion] if conclusion else [])
    if not nodes:
        return 0.0
    avg = sum(n.confidence for n in nodes) / len(nodes)
    err = sum(1 for i in issues if i.severity == "error")
    return round(max(0.0, avg - 0.05 * err), 3)
