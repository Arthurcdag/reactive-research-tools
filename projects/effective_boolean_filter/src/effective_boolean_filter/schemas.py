from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional
import uuid


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
    "fallacy_fallacy",
    "modal_shift",
    "temporal_shift",
]

Strictness = Literal["low", "medium", "high"]

ContradictionStatus = Literal[
    "none",
    "contained",
    "conclusion_dependent",
    "scope_resolved",
    "temporal_resolved",
    "definition_resolved",
    "breaking",
]

NegationType = Literal[
    "logical",
    "epistemic",
    "modal",
    "ability",
    "permission",
    "unknown",
]

ProbeType = Literal[
    "invert_premise",
    "weaken_premise",
    "remove_premise",
    "swap_definition",
    "ask_falsifier",
    "ask_implementation",
    "ask_prediction",
    "ask_counterexample",
    "ask_dependency",
    "ask_measurable_effect",
]

Recommendation = Literal[
    "accept",
    "accept_with_caveats",
    "needs_testing",
    "reject",
    "needs_clarification",
]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class ArgumentInput:
    claim: str
    argument: str
    context: str = ""
    task: str = "argument evaluation"
    strictness: Strictness = "medium"


@dataclass
class ClaimNode:
    text: str
    normalized_form: str
    object_id: str = "P"
    scope: str = "general"
    context_id: str = "default"
    definition_id: str = "default"
    polarity: Polarity = "unknown"
    confidence: float = 0.0
    negation_type: NegationType = "unknown"
    negation_count: int = 0
    is_premise: bool = True
    is_conclusion: bool = False
    id: str = field(default_factory=lambda: _new_id("c"))


@dataclass
class TransformationStep:
    from_node: str
    to_node: str
    transformation_type: Transformation
    tracked: bool
    reason: str
    invariants_held: bool = True


@dataclass
class Issue:
    code: str
    message: str
    severity: Literal["info", "warn", "error"] = "warn"
    related_node_ids: list[str] = field(default_factory=list)


@dataclass
class Probe:
    type: ProbeType
    question: str
    purpose: str
    expected_failure_mode: str = ""
    targets_node_id: Optional[str] = None
    answer: Optional[str] = None
    passed: Optional[bool] = None


@dataclass
class ScoreVector:
    negation_consistency: float = 1.0
    scope_preservation: float = 1.0
    definition_stability: float = 1.0
    context_fit: float = 1.0
    contradiction_containment: float = 1.0
    reactive_performance: float = 0.5
    testability: float = 0.5
    implementation_relevance: float = 0.5
    reasons: dict[str, list[str]] = field(default_factory=dict)

    def add_reason(self, field_name: str, reason: str) -> None:
        self.reasons.setdefault(field_name, []).append(reason)

    def to_dict(self) -> dict[str, float | dict[str, list[str]]]:
        return {
            "negation_consistency": self.negation_consistency,
            "scope_preservation": self.scope_preservation,
            "definition_stability": self.definition_stability,
            "context_fit": self.context_fit,
            "contradiction_containment": self.contradiction_containment,
            "reactive_performance": self.reactive_performance,
            "testability": self.testability,
            "implementation_relevance": self.implementation_relevance,
            "reasons": self.reasons,
        }


@dataclass
class ContradictionReport:
    status: ContradictionStatus = "none"
    pairs: list[tuple[str, str]] = field(default_factory=list)
    reason: str = ""


@dataclass
class EvaluationReport:
    effective_polarity: Polarity
    effectiveness_score: float
    bogusness_score: float
    score_vector: ScoreVector
    claims: list[ClaimNode] = field(default_factory=list)
    trace: list[TransformationStep] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    probes: list[Probe] = field(default_factory=list)
    contradiction: ContradictionReport = field(default_factory=ContradictionReport)
    recommendation: Recommendation = "needs_testing"
    confidence: float = 0.0
    id: str = field(default_factory=lambda: _new_id("eval"))
    input: Optional[ArgumentInput] = None
