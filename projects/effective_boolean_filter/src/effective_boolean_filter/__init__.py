"""Effective Boolean Argument Filter.

A traceable argument-effect filter, not a truth oracle.

Core rule: no untracked polarity shifts. ``not not P`` may reduce to
``effective_yes`` only when object, scope, definition, context, and
negation type are preserved. ``no evidence against P`` is epistemic
absence-of-disproof and must not collapse into ``not not P``.
"""
from .engine import evaluate_argument
from .probes import generate_probes
from .report import to_human, to_json_dict
from .advisory import (
    AdvisoryCandidate,
    AdvisoryRun,
    CandidateEvaluation,
    NyahlothepSelection,
    advisory_run_to_dict,
    azatoth_generate,
    nyahlothep_select,
    run_advisory_wrapper,
)
from .schemas import (
    ArgumentInput,
    ClaimNode,
    ContradictionReport,
    EvaluationReport,
    Issue,
    Polarity,
    Probe,
    ScoreVector,
    Strictness,
    TransformationStep,
)

__all__ = [
    "ArgumentInput",
    "AdvisoryCandidate",
    "AdvisoryRun",
    "CandidateEvaluation",
    "ClaimNode",
    "ContradictionReport",
    "EvaluationReport",
    "Issue",
    "NyahlothepSelection",
    "Polarity",
    "Probe",
    "ScoreVector",
    "Strictness",
    "TransformationStep",
    "advisory_run_to_dict",
    "azatoth_generate",
    "evaluate_argument",
    "generate_probes",
    "nyahlothep_select",
    "run_advisory_wrapper",
    "to_human",
    "to_json_dict",
]
