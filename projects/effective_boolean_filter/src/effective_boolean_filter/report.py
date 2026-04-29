"""Report layer.

Two output formats:
  - to_json_dict: stable JSON shape consumed by the API and tests
  - to_human:    a human-readable summary for the CLI
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .schemas import EvaluationReport


def to_json_dict(report: EvaluationReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "effective_polarity": report.effective_polarity,
        "effectiveness_score": report.effectiveness_score,
        "bogusness_score": report.bogusness_score,
        "confidence": report.confidence,
        "recommendation": report.recommendation,
        "score_vector": report.score_vector.to_dict(),
        "claims": [asdict(c) for c in report.claims],
        "trace": [asdict(s) for s in report.trace],
        "issues": [asdict(i) for i in report.issues],
        "probes": [asdict(p) for p in report.probes],
        "contradiction": asdict(report.contradiction),
        "input": asdict(report.input) if report.input else None,
    }


def to_human(report: EvaluationReport) -> str:
    lines: list[str] = []
    lines.append(f"Effective polarity: {report.effective_polarity}")
    lines.append(f"Effectiveness score: {report.effectiveness_score}")
    lines.append(f"Bogusness score: {report.bogusness_score}")
    lines.append(f"Recommendation: {report.recommendation}")
    lines.append(f"Confidence: {report.confidence}")
    lines.append("")
    if report.issues:
        lines.append("Detected issues:")
        for i in report.issues:
            lines.append(f"  - [{i.severity}] {i.code}: {i.message}")
        lines.append("")
    if report.contradiction.status != "none":
        lines.append(f"Contradiction status: {report.contradiction.status}")
        if report.contradiction.reason:
            lines.append(f"  reason: {report.contradiction.reason}")
        lines.append("")
    lines.append("Detected structure:")
    for c in report.claims:
        role = "conclusion" if c.is_conclusion else "premise"
        lines.append(
            f"  - ({role}) {c.text!r} -> {c.normalized_form} "
            f"[scope={c.scope}, neg_type={c.negation_type}, neg^{c.negation_count}]"
        )
    lines.append("")
    lines.append("Trace:")
    for s in report.trace:
        marker = "ok" if s.tracked else "UNTRACKED"
        lines.append(f"  - [{marker}] {s.transformation_type}: {s.reason}")
    lines.append("")
    lines.append("Score breakdown:")
    sv = report.score_vector
    for f in (
        "negation_consistency",
        "scope_preservation",
        "definition_stability",
        "context_fit",
        "contradiction_containment",
        "reactive_performance",
        "testability",
        "implementation_relevance",
    ):
        val = getattr(sv, f)
        reasons = sv.reasons.get(f, [])
        rstr = ("; ".join(reasons)) if reasons else "—"
        lines.append(f"  {f}: {val:.2f}  ({rstr})")
    lines.append("")
    lines.append("Recommended probes:")
    for i, p in enumerate(report.probes, 1):
        lines.append(f"  {i}. [{p.type}] {p.question}")
        lines.append(f"     purpose: {p.purpose}; failure mode: {p.expected_failure_mode}")
    return "\n".join(lines)
