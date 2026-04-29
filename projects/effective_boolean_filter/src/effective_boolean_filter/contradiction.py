"""Contradiction containment.

Spec section 7. We never apply explosion. When P and not(P) appear, we
classify the pair, decide whether the conclusion *depends* on it, and
record a containment status. The scoring layer reads this status; it
does not auto-discard.
"""
from __future__ import annotations

import re

from .schemas import (
    ClaimNode,
    ContradictionReport,
    ContradictionStatus,
    Issue,
)


SCOPE_KEYS = {"simulation", "production", "implementation", "legal", "physical"}
TEMPORAL_RE = re.compile(
    r"\b(yesterday|today|tomorrow|previously|now|currently|in\s+\d{4})\b",
    re.I,
)


# Antonym pairs: appearance of one root in node A and the other in node B
# is treated as a polarity flip on a shared concept.
ANTONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("works", "fails"),
    ("works", "failed"),
    ("succeeds", "fails"),
    ("succeeds", "failed"),
    ("up", "down"),
    ("safe", "unsafe"),
    ("safe", "dangerous"),
    ("true", "false"),
    ("correct", "incorrect"),
    ("present", "absent"),
)


def _antonym_concept(text: str) -> tuple[str, bool] | None:
    """Return (canonical_root, flipped) if text contains one half of an antonym pair."""
    lower = text.lower()
    for a, b in ANTONYM_PAIRS:
        if re.search(rf"\b{a}\b", lower):
            return (a, False)
        if re.search(rf"\b{b}\b", lower):
            return (a, True)
    return None


def _types_compatible(a: str, b: str) -> bool:
    return a == b or a == "unknown" or b == "unknown"


def _is_negation_of(a: ClaimNode, b: ClaimNode) -> bool:
    if a.object_id == b.object_id and _types_compatible(a.negation_type, b.negation_type):
        if (a.negation_count + b.negation_count) % 2 == 1:
            return True
    ca = _antonym_concept(a.text)
    cb = _antonym_concept(b.text)
    if ca is not None and cb is not None and ca[0] == cb[0] and ca[1] != cb[1]:
        return True
    return False


def _classify_pair(a: ClaimNode, b: ClaimNode) -> ContradictionStatus:
    if a.scope != b.scope and (a.scope in SCOPE_KEYS or b.scope in SCOPE_KEYS):
        return "scope_resolved"
    if a.definition_id != b.definition_id:
        return "definition_resolved"
    if TEMPORAL_RE.search(a.text) or TEMPORAL_RE.search(b.text):
        return "temporal_resolved"
    return "contained"


def _conclusion_depends_on_pair(
    conclusion: ClaimNode | None,
    a: ClaimNode,
    b: ClaimNode,
) -> bool:
    if conclusion is None:
        return False
    obj = conclusion.object_id
    candidates = (a.object_id, b.object_id)
    if obj in candidates:
        return True
    # substring overlap to handle "P" vs "P holds"
    for c in candidates:
        if c and (c in obj or obj in c):
            return True
    return False


def detect_contradictions(
    premises: list[ClaimNode],
    conclusion: ClaimNode | None,
) -> tuple[ContradictionReport, list[Issue]]:
    issues: list[Issue] = []
    pairs: list[tuple[str, str]] = []
    statuses: list[ContradictionStatus] = []

    for i in range(len(premises)):
        for j in range(i + 1, len(premises)):
            a, b = premises[i], premises[j]
            if not _is_negation_of(a, b):
                continue
            pairs.append((a.id, b.id))
            status = _classify_pair(a, b)
            if _conclusion_depends_on_pair(conclusion, a, b) and status == "contained":
                status = "conclusion_dependent"
            statuses.append(status)
            severity = "error" if status in ("conclusion_dependent", "breaking") else "warn"
            issues.append(
                Issue(
                    code=f"contradiction_{status}",
                    message=(
                        f"contradictory premises on {a.object_id!r}: "
                        f"{a.text!r} vs {b.text!r} ({status})"
                    ),
                    severity=severity,
                    related_node_ids=[a.id, b.id],
                )
            )

    if not pairs:
        return ContradictionReport(status="none"), issues

    # combine: worst wins
    severity_order: list[ContradictionStatus] = [
        "scope_resolved",
        "temporal_resolved",
        "definition_resolved",
        "contained",
        "conclusion_dependent",
        "breaking",
    ]
    worst = max(statuses, key=severity_order.index)
    reason = f"{len(pairs)} contradictory pair(s); worst status: {worst}"
    return ContradictionReport(status=worst, pairs=pairs, reason=reason), issues
