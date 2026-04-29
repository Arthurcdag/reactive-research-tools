"""Scope shift detection.

Spec section 4.3 calls out three named patterns we must detect:
  - legal_impossibility -> physical_possibility (without bridge)
  - simulation -> production (without bridge)
  - epistemic -> ontological (covered in polarity.py via negation_type)

A "bridge premise" is a tracked premise whose object_id matches and which
explicitly licenses crossing the scope boundary, e.g. "the simulation has
been validated against production data".
"""
from __future__ import annotations

import re

from .schemas import ClaimNode, Issue, TransformationStep


# (premise_scope, conclusion_scope) -> (issue_code, human_message)
SCOPE_BRIDGE_REQUIRED: dict[tuple[str, str], tuple[str, str]] = {
    ("legal", "physical"): (
        "legal_to_physical_scope_shift",
        "legal possibility does not entail physical possibility without a bridge",
    ),
    ("legal", "implementation"): (
        "legal_to_physical_scope_shift",
        "legal status does not entail safe implementation without a bridge",
    ),
    ("legal", "general"): (
        "legal_to_physical_scope_shift",
        "legal status does not entail an ontological claim without a bridge",
    ),
    ("legal", "modal_possibility"): (
        "legal_to_physical_scope_shift",
        "legal status does not entail physical possibility without a bridge",
    ),
    ("legal", "production"): (
        "legal_to_physical_scope_shift",
        "legal status does not entail safe behaviour in production without a bridge",
    ),
    ("simulation", "production"): (
        "simulation_to_production_scope_shift",
        "simulation results do not entail production behaviour without a bridge",
    ),
    ("simulation", "implementation"): (
        "simulation_to_production_scope_shift",
        "simulation does not entail real-world implementation without a bridge",
    ),
    ("simulation", "physical"): (
        "simulation_to_production_scope_shift",
        "simulation does not entail physical/real-world behaviour without a bridge",
    ),
    ("simulation", "general"): (
        "simulation_to_production_scope_shift",
        "simulation does not entail an ontological real-world claim without a bridge",
    ),
    ("modal_possibility", "production"): (
        "possibility_to_actuality_scope_shift",
        "possibility does not entail actuality without a bridge",
    ),
    ("modal_possibility", "physical"): (
        "possibility_to_actuality_scope_shift",
        "possibility does not entail physical actuality without a bridge",
    ),
    ("modal_possibility", "general"): (
        "possibility_to_actuality_scope_shift",
        "possibility does not entail an ontological actuality without a bridge",
    ),
}

BRIDGE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bvalidated\s+against\b",
        r"\bcalibrated\s+(?:to|against)\b",
        r"\bverified\s+against\b",
        r"\bmatches\s+production\b",
        r"\btested\s+in\s+production\b",
        r"\bconfirmed\s+in\s+production\b",
        r"\bcorrelates\s+with\s+production\b",
    )
]


def has_bridge_premise(premises: list[ClaimNode]) -> bool:
    for p in premises:
        text = p.text
        if any(rx.search(text) for rx in BRIDGE_PATTERNS):
            return True
    return False


def detect_scope_shifts(
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
) -> tuple[list[TransformationStep], list[Issue]]:
    if conclusion is None:
        return [], []

    steps: list[TransformationStep] = []
    issues: list[Issue] = []
    bridge = has_bridge_premise(premises)

    for prem in premises:
        key = (prem.scope, conclusion.scope)
        if key not in SCOPE_BRIDGE_REQUIRED:
            continue
        code, msg = SCOPE_BRIDGE_REQUIRED[key]
        if bridge:
            steps.append(
                TransformationStep(
                    from_node=prem.id,
                    to_node=conclusion.id,
                    transformation_type="scope_shift",
                    tracked=True,
                    reason=f"{prem.scope} -> {conclusion.scope} but bridge premise found",
                    invariants_held=True,
                )
            )
            continue
        steps.append(
            TransformationStep(
                from_node=prem.id,
                to_node=conclusion.id,
                transformation_type="scope_shift",
                tracked=False,
                reason=f"{prem.scope} -> {conclusion.scope} without bridge premise",
                invariants_held=False,
            )
        )
        issues.append(
            Issue(
                code=code,
                message=msg,
                severity="error",
                related_node_ids=[prem.id, conclusion.id],
            )
        )
    return steps, issues


_STRONG_CONCLUSION_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bproves?\b",
        r"\bis\s+true\b",
        r"\bis\s+correct\b",
        r"\bis\s+proven\b",
        r"\bis\s+established\b",
        r"\bis\s+the\s+best\b",
        r"\bwill\s+happen\b",
        r"\bwill\s+work\b",
        r"\b(?:must|surely|certainly)\b",
        r"\bfollows?\b",
        r"\bis\s+(?:safe|secure|effective)\b",
        r"\bis\s+(?:false|wrong|incorrect|fake)\b",
        r"\bscales?\b",
    )
]


_FALLACY_PREMISE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\b(weak|fallacious|bad|flawed)\s+(premise|argument)\b",
        r"\bone\s+(?:climate\s+)?(?:model|study|paper|test)\s+(?:is\s+)?(?:wrong|fails|failed)\b",
    )
]


def detect_unsupported_strengthening(
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
) -> list[Issue]:
    """Conclusion stronger than premises (Section 4.3 / Section 16).

    Heuristic: conclusion is "strong" (asserts truth/falsity/safety/inevitability)
    while premises only carry epistemic absence-of-disproof, possibility, or
    fallacy-fallacy patterns.
    """
    if conclusion is None:
        return []
    text = conclusion.text.lower()
    strong = any(p.search(text) for p in _STRONG_CONCLUSION_PATTERNS)
    if not strong:
        return []
    issues: list[Issue] = []
    if not premises:
        issues.append(
            Issue(
                code="unsupported_strengthening",
                message="conclusion asserts a strong claim but no supporting premises were parsed",
                severity="error",
                related_node_ids=[conclusion.id],
            )
        )
        return issues

    if all(p.negation_type == "epistemic" for p in premises):
        issues.append(
            Issue(
                code="unsupported_strengthening",
                message="conclusion claims proof but premises only carry epistemic absence-of-evidence",
                severity="error",
                related_node_ids=[conclusion.id, *(p.id for p in premises)],
            )
        )

    # fallacy-fallacy: premise about premise quality, conclusion declares falsity
    if re.search(r"\b(false|wrong|incorrect|fake)\b", text):
        for p in premises:
            if any(rx.search(p.text) for rx in _FALLACY_PREMISE_PATTERNS):
                issues.append(
                    Issue(
                        code="unsupported_strengthening",
                        message="fallacy fallacy: a weak premise does not refute the conclusion",
                        severity="error",
                        related_node_ids=[conclusion.id, p.id],
                    )
                )
                break

    # possibility -> actuality / strong assertion
    if any(p.scope == "modal_possibility" for p in premises) and re.search(
        r"\b(will|is\s+the\s+best|is\s+safe|is\s+effective|is\s+true)\b", text
    ):
        issues.append(
            Issue(
                code="unsupported_strengthening",
                message="conclusion treats mere possibility as actuality",
                severity="error",
                related_node_ids=[conclusion.id],
            )
        )

    # number-too-small: premise reports a measurement at one scale, conclusion claims another
    if re.search(r"\b(scale|million|billion|thousand)\b", text) and any(
        re.search(r"\b(thousand|hundred|few|small|sample)\b", p.text.lower()) for p in premises
    ):
        issues.append(
            Issue(
                code="unsupported_strengthening",
                message="conclusion extrapolates beyond the measured scale",
                severity="error",
                related_node_ids=[conclusion.id],
            )
        )

    # "P does not imply Q. Therefore Q follows." — strengthening over an explicit denial
    for p in premises:
        if re.search(r"\bdoes\s+not\s+imply\b", p.text, re.I) and re.search(
            r"\b(follows?|therefore|proves?)\b", text
        ):
            issues.append(
                Issue(
                    code="unsupported_strengthening",
                    message="conclusion claims to follow despite an explicit non-implication premise",
                    severity="error",
                    related_node_ids=[conclusion.id, p.id],
                )
            )
            break

    return issues
