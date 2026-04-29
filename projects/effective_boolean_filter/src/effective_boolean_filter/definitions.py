"""Definition / equivocation tracker.

Spec section 17 demands that key terms be tracked with versioned
``definition_id`` so that swapped meanings of the same word are visible.

We do not run an NLP synonym resolver. Instead we look for surface
re-definition patterns ("by X we mean ...") and equivocation patterns
where the same term is used in two clearly distinct keyword clusters.
"""
from __future__ import annotations

import re

from .schemas import ClaimNode, Issue


REDEFINITION_RE = re.compile(
    r"\b(?:by|where|here)\b\s+(?P<term>[\w-]+)\s+(?:we\s+mean|means|refers to|=)\s+",
    re.I,
)


KEY_TERM_CLUSTERS: dict[str, dict[str, tuple[str, ...]]] = {
    # term -> sense_id -> trigger keywords for that sense
    "works": {
        "simulation": ("simulation", "model", "lab", "in vitro", "benchmark"),
        "production": ("production", "real world", "in practice", "deployment", "live"),
    },
    "secure": {
        "theoretical": ("in theory", "in principle", "abstractly"),
        "operational": ("in practice", "deployed", "in production", "real world"),
    },
    "possible": {
        "legal": ("legal", "legally", "law"),
        "physical": ("physical", "physically", "physics"),
    },
}


def find_term_redefinitions(text: str) -> list[str]:
    return [m.group("term").lower() for m in REDEFINITION_RE.finditer(text)]


def detect_definition_shifts(nodes: list[ClaimNode]) -> list[Issue]:
    """Flag a term used in two different sense clusters across the argument."""
    issues: list[Issue] = []
    for term, senses in KEY_TERM_CLUSTERS.items():
        sense_hits: dict[str, list[str]] = {}
        for n in nodes:
            text = n.text.lower()
            if not re.search(rf"\b{re.escape(term)}\b", text):
                continue
            for sense_id, keywords in senses.items():
                if any(k in text for k in keywords):
                    sense_hits.setdefault(sense_id, []).append(n.id)
                    n.definition_id = f"{term}:{sense_id}"
                    break
        if len(sense_hits) >= 2:
            related: list[str] = []
            for ids in sense_hits.values():
                related.extend(ids)
            issues.append(
                Issue(
                    code="definition_shift",
                    message=(
                        f"term {term!r} used in incompatible senses: "
                        + ", ".join(sense_hits.keys())
                    ),
                    severity="error",
                    related_node_ids=related,
                )
            )
    return issues
