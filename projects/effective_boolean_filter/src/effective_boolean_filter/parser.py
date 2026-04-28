from __future__ import annotations

import re
from .schemas import ClaimNode


EPISTEMIC_PATTERNS = [
    re.compile(r"\bno evidence (that |for |against )", re.I),
    re.compile(r"\bnot known\b", re.I),
    re.compile(r"\bnot proven\b", re.I),
    re.compile(r"\bno one (has )?(disproved|refuted)\b", re.I),
]

DOUBLE_NEGATION_PATTERNS = [
    re.compile(r"\bnot\s+(?:the case\s+)?(?:that\s+)?not\b", re.I),
    re.compile(r"\bnot\s+false\b", re.I),
]

NEGATION_PATTERNS = [
    re.compile(r"\bnot\b", re.I),
    re.compile(r"\bno\b", re.I),
    re.compile(r"\bnever\b", re.I),
    re.compile(r"\bfalse\b", re.I),
]


def detect_scope(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["evidence", "known", "proven", "disproved", "believe"]):
        return "epistemic"
    if any(w in lower for w in ["legal", "law", "allowed"]):
        return "legal"
    if any(w in lower for w in ["physical", "physics", "possible in theory"]):
        return "physical"
    if any(w in lower for w in ["production", "implementation", "works in practice"]):
        return "practical"
    if any(w in lower for w in ["simulation", "model"]):
        return "simulation"
    return "general"


def parse_claim(text: str) -> ClaimNode:
    stripped = text.strip()
    parsed = stripped
    polarity = "unknown"
    confidence = 0.3

    if any(p.search(stripped) for p in EPISTEMIC_PATTERNS):
        parsed = "epistemic_negation"
        polarity = "unknown"
        confidence = 0.8
    elif any(p.search(stripped) for p in DOUBLE_NEGATION_PATTERNS):
        parsed = "not not P"
        polarity = "effective_yes"
        confidence = 0.7
    else:
        negs = sum(1 for p in NEGATION_PATTERNS if p.search(stripped))
        if negs == 0:
            parsed = "P"
            polarity = "effective_yes"
            confidence = 0.4
        elif negs % 2 == 0:
            parsed = "N^even(P)"
            polarity = "effective_yes"
            confidence = 0.5
        else:
            parsed = "N^odd(P)"
            polarity = "effective_no"
            confidence = 0.5

    return ClaimNode(
        text=stripped,
        parsed_form=parsed,
        polarity=polarity,
        scope=detect_scope(stripped),
        object_id="P",
        confidence=confidence,
    )


def split_argument(argument: str) -> list[str]:
    parts = re.split(r"(?:\.|;|\n|\btherefore\b|\bso\b|\bbecause\b)", argument, flags=re.I)
    return [p.strip() for p in parts if p.strip()]
