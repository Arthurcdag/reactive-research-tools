from __future__ import annotations

from dataclasses import asdict
import re

from .parser import parse_claim, split_argument
from .schemas import ProbeResult, TransformationStep


def detect_issues(claim: str, argument: str, claims) -> list[str]:
    issues: list[str] = []
    text = f"{claim} {argument}".lower()

    if "no evidence" in text and any(w in text for w in ["therefore", "proves", "true"]):
        issues.append("epistemic-to-ontological shift")
        issues.append("absence of disproof treated as proof")

    if any(w in text for w in ["simulation"]) and any(w in text for w in ["production", "practice"]):
        issues.append("scope shift: simulation/theory to production/practice")

    scopes = {c.scope for c in claims}
    if len(scopes) > 1 and "epistemic" in scopes:
        issues.append("scope instability across premises")

    if re.search(r"\bproves?\b", text) and any(w in text for w in ["no evidence", "not disproved", "not proven false"]):
        issues.append("conclusion stronger than premises")

    if "not not not" in text or "no no no" in text:
        issues.append("odd negation parity cannot resolve to yes without a tracked rule shift")

    return sorted(set(issues))


def generate_probes(issues: list[str], claim: str) -> list[ProbeResult]:
    probes = [
        ProbeResult(
            probe="What would falsify the claim?",
            purpose="testability",
            expected_failure_mode="missing falsifier",
        ),
        ProbeResult(
            probe="Does the conclusion still follow if absence-of-disproof is removed?",
            purpose="dependency check",
            expected_failure_mode="argument depends on epistemic absence",
        ),
        ProbeResult(
            probe="Can the claim produce a concrete prediction or implementation result?",
            purpose="reactive performance",
            expected_failure_mode="no measurable effect",
        ),
    ]

    if any("scope" in i for i in issues):
        probes.append(ProbeResult(
            probe="Does the conclusion preserve the same scope as the premise?",
            purpose="scope preservation",
            expected_failure_mode="scope jump",
        ))
    if any("epistemic" in i for i in issues):
        probes.append(ProbeResult(
            probe="Is 'not known false' being converted into 'true'?",
            purpose="negation-type audit",
            expected_failure_mode="epistemic-to-ontological shift",
        ))

    probes.append(ProbeResult(
        probe=f"What would be an operational test of: {claim}",
        purpose="contextual effectiveness",
        expected_failure_mode="no task-level effect",
    ))

    return probes[:6]


def score(issues: list[str], claims) -> tuple[dict[str, float], float, float, str]:
    negation_consistency = 1.0
    scope_preservation = 1.0
    definition_stability = 0.8
    context_fit = 0.7
    contradiction_containment = 0.8
    reactive_performance = 0.5
    testability = 0.5
    implementation_relevance = 0.5

    if any("epistemic" in i or "negation" in i for i in issues):
        negation_consistency -= 0.45
    if any("scope" in i for i in issues):
        scope_preservation -= 0.45
    if any("stronger than premises" in i for i in issues):
        context_fit -= 0.25
        testability -= 0.15
    if any("absence of disproof" in i for i in issues):
        reactive_performance -= 0.20

    vals = {
        "negation_consistency": max(0.0, negation_consistency),
        "scope_preservation": max(0.0, scope_preservation),
        "definition_stability": max(0.0, definition_stability),
        "context_fit": max(0.0, context_fit),
        "contradiction_containment": max(0.0, contradiction_containment),
        "reactive_performance": max(0.0, reactive_performance),
        "testability": max(0.0, testability),
        "implementation_relevance": max(0.0, implementation_relevance),
    }

    overall = (
        0.20 * vals["negation_consistency"]
        + 0.15 * vals["scope_preservation"]
        + 0.15 * vals["definition_stability"]
        + 0.15 * vals["context_fit"]
        + 0.10 * vals["contradiction_containment"]
        + 0.15 * vals["reactive_performance"]
        + 0.10 * vals["testability"]
    )

    bogusness = 1.0 - overall

    if any("epistemic-to-ontological" in i for i in issues):
        polarity = "untracked_shift"
    elif issues:
        polarity = "unstable"
    else:
        polarity = "effective_yes"

    return vals, round(overall, 3), round(bogusness, 3), polarity


def build_trace(claims) -> list[TransformationStep]:
    trace = []
    for c in claims:
        warning = ""
        valid = True
        transformation = "valid_inference"

        if c.parsed_form == "epistemic_negation":
            transformation = "epistemic_to_ontological_shift"
            valid = False
            warning = "epistemic negation must not be reduced to ontological affirmation"

        trace.append(TransformationStep(
            source=c.text,
            target=c.parsed_form,
            transformation=transformation,
            valid=valid,
            warning=warning,
        ))
    return trace


def evaluate_argument(
    claim: str,
    argument: str,
    context: str = "",
    task: str = "argument evaluation",
    strictness: str = "medium",
) -> dict:
    nodes = [parse_claim(part) for part in split_argument(argument)]
    nodes.insert(0, parse_claim(claim))

    issues = detect_issues(claim, argument, nodes)
    score_breakdown, effectiveness, bogusness, polarity = score(issues, nodes)
    probes = generate_probes(issues, claim)
    trace = build_trace(nodes)

    return {
        "effective_polarity": polarity,
        "effectiveness_score": effectiveness,
        "bogusness_score": bogusness,
        "claim": claim,
        "context": context,
        "task": task,
        "strictness": strictness,
        "claims": [asdict(n) for n in nodes],
        "trace": [asdict(t) for t in trace],
        "issues": issues,
        "probes": [asdict(p) for p in probes],
        "score_breakdown": score_breakdown,
        "recommendation": "needs testing" if issues else "structurally acceptable for MVP",
    }
