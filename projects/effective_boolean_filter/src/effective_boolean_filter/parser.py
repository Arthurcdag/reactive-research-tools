"""Parser for the controlled phrase set in spec Section 6.

The parser is intentionally rule-based and conservative. It extracts:
  - logical negations
  - epistemic negations (no evidence / not known / not proven / no one disproved)
  - modal terms (legal, physical, possible, impossible, allowed)
  - scope markers (simulation, production, in theory, in practice)
  - implication / failure markers (implies, does not imply, failed to disprove)
  - conclusion markers (therefore, so, thus, hence, because)

It is the only place that converts surface text into normalized forms.
The polarity engine downstream owns the verdict; parser output is advisory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ClaimNode, NegationType


CONCLUSION_MARKERS = re.compile(
    r"\b(therefore|hence|thus|so that|so |it follows that|we conclude|proves that|proves)\b",
    re.I,
)

PREMISE_SPLIT_RE = re.compile(
    r"(?:\.|;|\n|\btherefore\b|\bhence\b|\bthus\b|\bso\b|\bbecause\b|\bsince\b)",
    re.I,
)

EPISTEMIC_PATTERNS = [
    (re.compile(r"\bno\s+evidence\s+(?:has\s+been\s+(?:brought|found|presented|provided)\s+)?(?:that|for)\s+(?P<obj>.+)$", re.I), "not_known_evidence_for"),
    (re.compile(r"\bno\s+evidence\s+against\s+(?P<obj>.+)$", re.I), "not_known_not"),
    (re.compile(r"\b(?:no\s+one|nobody)\s+(?:has\s+|can\s+)?(?:disproved?|refuted?|proven?|proved|shown)\s+(?P<obj>.+)$", re.I), "not_known_not"),
    (re.compile(r"\b(?:you|we|science|anyone)\s+cannot\s+(?:dis)?prove\s+(?P<obj>.+)$", re.I), "not_known_not"),
    (re.compile(r"\bcannot\s+(?:be\s+)?(?:dis)?proved?\b", re.I), "not_known"),
    (re.compile(r"\bnot\s+known\s+(?:that\s+)?(?P<obj>.+)$", re.I), "not_known"),
    (re.compile(r"\bnot\s+proven\s+(?:that\s+)?(?P<obj>.+)$", re.I), "not_proven"),
    (re.compile(r"\bfailed\s+to\s+disprove\s+(?P<obj>.+)$", re.I), "failed_disprove"),
    (re.compile(r"\bcannot\s+be\s+tested\b", re.I), "not_known"),
    # bare weak-evidence markers
    (re.compile(r"\b(?:explains\s+everything|everyone\s+knows|intuit(?:ion|ively)|obviously)\b", re.I), "weak_evidence"),
]

MODAL_PATTERNS = [
    (re.compile(r"\bnot\s+legally\s+impossible\b", re.I), "not_legally_impossible"),
    (re.compile(r"\blegally\s+impossible\b", re.I), "legally_impossible"),
    (re.compile(r"\bphysically\s+possible\b", re.I), "physically_possible"),
    (re.compile(r"\bphysically\s+impossible\b", re.I), "physically_impossible"),
    (re.compile(r"\bin\s+principle\b", re.I), "in_principle"),
    (re.compile(r"\bin\s+practice\b", re.I), "in_practice"),
]

# match "not the case that not P" before generic "not" so we don't double count
DOUBLE_NEGATION_RE = re.compile(
    r"\b(?:it\s+is\s+)?not\s+(?:the\s+case\s+that\s+|that\s+)?(?:it\s+is\s+)?not\b",
    re.I,
)
TRIPLE_NEGATION_RE = re.compile(
    r"\bnot\s+(?:the\s+case\s+that\s+)?not\s+(?:the\s+case\s+that\s+)?not\b",
    re.I,
)
NOT_FALSE_RE = re.compile(r"\bnot\s+false\b", re.I)
SIMPLE_NOT_RE = re.compile(r"\b(?:not|never|no(?!t))\b", re.I)
DOES_NOT_IMPLY_RE = re.compile(r"\bdoes\s+not\s+imply\b", re.I)
IT_IS_FALSE_RE = re.compile(r"\bit\s+is\s+false\s+that\b", re.I)
FALLACY_FALLACY_RE = re.compile(
    r"\b(weak|fallacious|bad)\s+(premise|argument)\b.*\b(therefore|so|thus)\b.*\b(false|wrong|incorrect)\b",
    re.I,
)


SCOPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "epistemic": ("evidence", "known", "proven", "disproved", "believe", "refuted"),
    "legal": ("legal", "legally", "law", "lawful", "allowed", "permitted", "forbidden",
              "legally impossible"),
    # "in practice" / "achievable" / "is safe" all imply real-world / physical scope
    "physical": ("physical", "physically", "physics", "in practice", "is safe", "achievable",
                 "is secure in practice", "real world", "real-world"),
    "modal_possibility": ("in principle", "in theory", "possible in theory",
                          "is possible", "possibly", "could ", "might "),
    "simulation": ("simulation", "simulated", "in simulation", "in mice", "lab",
                   "in vitro", "benchmark"),
    "production": ("production", "in production", "deployment", "deployed", "live"),
    "implementation": ("implementation", "implement", "deploy", "ship", "is safe to deploy"),
    "temporal": ("yesterday", "today", "tomorrow", "previously", "now", "currently"),
}


def detect_scope(text: str) -> str:
    lower = text.lower()
    # priority order: more specific scopes first. Legal beats production
    # because "legally impossible" is a specifically modal-legal claim even
    # if "deployment" is mentioned.
    priority = (
        "epistemic", "legal", "simulation", "modal_possibility",
        "production", "implementation", "physical", "temporal",
    )
    for scope_name in priority:
        if any(k in lower for k in SCOPE_KEYWORDS[scope_name]):
            return scope_name
    return "general"


def detect_negation_type(text: str) -> NegationType:
    lower = text.lower()
    if any(p.search(lower) for p, _ in EPISTEMIC_PATTERNS):
        return "epistemic"
    if any(w in lower for w in ("possible", "impossible", "must", "may", "might", "could", "can")):
        return "modal"
    if "allowed" in lower or "permitted" in lower or "forbidden" in lower:
        return "permission"
    if any(p.search(lower) for p, _ in MODAL_PATTERNS):
        return "modal"
    if SIMPLE_NOT_RE.search(lower) or IT_IS_FALSE_RE.search(lower):
        return "logical"
    return "unknown"


def _extract_object(text: str) -> str:
    """Extract the proposition the negation/claim is *about*.

    Coarse: strip leading discourse + negation words and a trailing ``therefore`` clause."""
    cleaned = re.sub(
        r"^\s*(it\s+is\s+|we\s+know\s+that\s+|note\s+that\s+|i\s+claim\s+that\s+)",
        "",
        text.strip(),
        flags=re.I,
    )
    cleaned = re.split(CONCLUSION_MARKERS, cleaned, maxsplit=1)[0]
    return cleaned.strip(" .,;:")


_OBJECT_STRIP_PREFIX = re.compile(
    r"^("
    r"that\s+|the\s+claim\s+that\s+|the\s+proposition\s+that\s+|"
    r"not\s+(?:the\s+case\s+that\s+|that\s+)?(?:it\s+is\s+)?(?:not\s+(?:the\s+case\s+that\s+|that\s+)?)?|"
    r"never\s+|no\s+"
    r")",
    re.I,
)
_OBJECT_STRIP_SUFFIX = re.compile(
    r"\s+(?:holds|is\s+true|is\s+correct|is\s+false|is\s+the\s+case)$",
    re.I,
)
_ANTONYM_NORMALISE: dict[str, str] = {
    # canonicalise antonym verbs to a single root + an implicit negation flag
    # we don't apply the flag here; contradiction.py uses the lexicon below
}


def _normalize_object(obj: str) -> str:
    """Stable identifier for an object so two phrasings of the same proposition match."""
    obj = obj.lower().strip(" .,;:'\"`")
    obj = re.sub(r"\s+", " ", obj)
    # repeatedly strip leading discourse / negation words
    while True:
        new = _OBJECT_STRIP_PREFIX.sub("", obj)
        if new == obj:
            break
        obj = new
    obj = _OBJECT_STRIP_SUFFIX.sub("", obj)
    return obj.strip()


def parse_claim(
    text: str,
    *,
    context_id: str = "default",
    is_conclusion: bool = False,
) -> ClaimNode:
    stripped = text.strip()
    lower = stripped.lower()

    normalized: str
    polarity = "unknown"
    confidence = 0.4
    negation_count = 0
    negation_type = detect_negation_type(stripped)
    obj_text = _extract_object(stripped)

    # 1. epistemic forms — must NOT collapse to ontological double negation
    epistemic_hit: tuple[str, str] | None = None
    for rx, kind in EPISTEMIC_PATTERNS:
        m = rx.search(stripped)
        if m:
            try:
                obj_inner = m.group("obj").strip(" .,;:")
            except IndexError:
                obj_inner = obj_text
            epistemic_hit = (kind, obj_inner)
            break

    if epistemic_hit:
        kind, obj_inner = epistemic_hit
        norm_obj = _normalize_object(obj_inner)
        if kind == "not_known_not":
            normalized = f"not known(not({norm_obj}))"
        elif kind == "not_known_evidence_for":
            normalized = f"not known(evidence_for({norm_obj}))"
        elif kind == "not_known":
            normalized = f"not known({norm_obj})"
        elif kind == "not_proven":
            normalized = f"not proven({norm_obj})"
        elif kind == "failed_disprove":
            normalized = f"failed(disprove({norm_obj}))"
        elif kind == "weak_evidence":
            normalized = f"weak_evidence({norm_obj})"
        else:
            normalized = f"epistemic({norm_obj})"
        polarity = "unknown"
        confidence = 0.85
        negation_type = "epistemic"
        return ClaimNode(
            text=stripped,
            normalized_form=normalized,
            object_id=norm_obj,
            scope="epistemic",
            context_id=context_id,
            definition_id="default",
            polarity=polarity,
            confidence=confidence,
            negation_type=negation_type,
            negation_count=1,
            is_conclusion=is_conclusion,
            is_premise=not is_conclusion,
        )

    # 2. modal forms — keep modal operator explicit
    for rx, kind in MODAL_PATTERNS:
        if rx.search(stripped):
            norm_obj = _normalize_object(obj_text)
            normalized = f"{kind}({norm_obj})" if "(" not in kind else kind
            return ClaimNode(
                text=stripped,
                normalized_form=normalized,
                object_id=norm_obj,
                scope=detect_scope(stripped),
                context_id=context_id,
                definition_id="default",
                polarity="unknown",
                confidence=0.7,
                negation_type="modal",
                negation_count=1 if "not" in lower else 0,
                is_conclusion=is_conclusion,
                is_premise=not is_conclusion,
            )

    # 3. logical negation parity. Count first, then choose normalized form.
    norm_obj = _normalize_object(obj_text)
    n_count = len(SIMPLE_NOT_RE.findall(stripped))
    if IT_IS_FALSE_RE.search(stripped):
        n_count += 1
    # "P is not false" is a semantic double negation: count the implicit
    # second negation in "false" so parity reduces to yes.
    if NOT_FALSE_RE.search(stripped):
        n_count += 1
    negation_count = n_count

    if n_count == 0:
        normalized = norm_obj
        polarity = "effective_yes"
        confidence = 0.55
    else:
        # parity decides polarity; normalized form decorates with the count
        if n_count % 2 == 0:
            polarity = "effective_yes"
            confidence = 0.7 if n_count == 2 else 0.55
        else:
            polarity = "effective_no"
            confidence = 0.7 if n_count == 1 else 0.55
        normalized = "not(" * n_count + norm_obj + ")" * n_count

    return ClaimNode(
        text=stripped,
        normalized_form=normalized,
        object_id=norm_obj,
        scope=detect_scope(stripped),
        context_id=context_id,
        definition_id="default",
        polarity=polarity,
        confidence=confidence,
        negation_type=negation_type,
        negation_count=negation_count,
        is_conclusion=is_conclusion,
        is_premise=not is_conclusion,
    )


@dataclass
class ParsedArgument:
    premises: list[ClaimNode]
    conclusion: ClaimNode | None
    raw_segments: list[str]


def split_argument(argument: str) -> list[str]:
    parts = PREMISE_SPLIT_RE.split(argument)
    return [p.strip() for p in parts if p.strip()]


def parse_argument(argument: str, *, context_id: str = "default") -> ParsedArgument:
    """Split an argument into premise nodes plus a conclusion node.

    A segment immediately preceded by a conclusion marker (therefore/hence/thus)
    becomes the conclusion. Otherwise the last non-trivial segment is taken
    as the conclusion. A single segment without a marker is itself the
    conclusion, with no premises.
    """
    segments = split_argument(argument)
    if not segments:
        return ParsedArgument(premises=[], conclusion=None, raw_segments=[])

    conclusion_idx: int | None = None
    cursor = 0
    for i, seg in enumerate(segments):
        idx = argument.lower().find(seg.lower(), cursor)
        if idx == -1:
            continue
        before = argument[:idx]
        if CONCLUSION_MARKERS.search(before[-40:] if len(before) > 40 else before):
            conclusion_idx = i
        cursor = idx + len(seg)
    if conclusion_idx is None:
        # fall back: last segment is the conclusion (also covers single-segment case)
        conclusion_idx = len(segments) - 1

    premise_nodes: list[ClaimNode] = []
    conclusion_node: ClaimNode | None = None
    for i, seg in enumerate(segments):
        is_conc = i == conclusion_idx
        node = parse_claim(seg, context_id=context_id, is_conclusion=is_conc)
        if is_conc:
            conclusion_node = node
        else:
            premise_nodes.append(node)
    return ParsedArgument(
        premises=premise_nodes,
        conclusion=conclusion_node,
        raw_segments=segments,
    )
