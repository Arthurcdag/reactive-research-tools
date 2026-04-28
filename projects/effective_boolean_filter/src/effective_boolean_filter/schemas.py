from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Polarity = Literal[
    "effective_yes",
    "effective_no",
    "unknown",
    "contradiction",
    "untracked_shift",
    "unstable",
]

Transformation = Literal[
    "negation",
    "double_negation",
    "scope_shift",
    "definition_shift",
    "context_shift",
    "epistemic_to_ontological_shift",
    "unsupported_strengthening",
    "valid_inference",
    "invalid_inference",
]


@dataclass
class ClaimNode:
    text: str
    parsed_form: str
    polarity: Polarity = "unknown"
    scope: str = "unknown"
    object_id: str = "unknown"
    confidence: float = 0.0


@dataclass
class TransformationStep:
    source: str
    target: str
    transformation: Transformation
    valid: bool
    warning: str = ""


@dataclass
class ProbeResult:
    probe: str
    purpose: str
    expected_failure_mode: str = ""


@dataclass
class EvaluationReport:
    effective_polarity: Polarity
    effectiveness_score: float
    bogusness_score: float
    trace: list[TransformationStep] = field(default_factory=list)
    claims: list[ClaimNode] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    probes: list[ProbeResult] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
