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
from .llm_client import (
    DeterministicFakeClient,
    DisabledLLMClientError,
    LLMClient,
    LLMProviderUnavailable,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    get_client,
)
from .llm_cache import (
    InputerCacheKey,
    LLMResponseCache,
    derive_cache_key,
    derive_inputer_cache_key,
)
from .llm_inputer import (
    InputerResult,
    InputerValidationError,
    default_pool_size,
    generate_inputer,
    inputer_result_to_dict,
    validate_inputer_payload,
)
from .llm_outputer import (
    OutputerResult,
    OutputerValidationError,
    generate_outputer,
    outputer_result_to_dict,
    validate_outputer_payload,
)
from .llm_prompts import (
    INPUTER_PROMPT_VERSION,
    PROMPT_VERSION,
    STYLES,
    render_inputer_prompt,
    render_prompt,
)
from .trace_gate import (
    GateReceipts,
    PipelineInvariantError,
    PipelineTrace,
    PromotionReceipt,
    RealityGateReceipt,
)
from .pulse_grab import (
    PULSE_GRAB_MODE,
    PulseGrabDecision,
    evaluate_pulse_grab,
    verify_pulse_grab_decision,
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
    "DeterministicFakeClient",
    "DisabledLLMClientError",
    "EvaluationReport",
    "GateReceipts",
    "INPUTER_PROMPT_VERSION",
    "InputerCacheKey",
    "InputerResult",
    "InputerValidationError",
    "Issue",
    "LLMClient",
    "LLMProviderUnavailable",
    "LLMRequest",
    "LLMResponse",
    "LLMResponseCache",
    "LLMTimeoutError",
    "NyahlothepSelection",
    "OutputerResult",
    "OutputerValidationError",
    "PULSE_GRAB_MODE",
    "PROMPT_VERSION",
    "PipelineInvariantError",
    "PipelineTrace",
    "Polarity",
    "Probe",
    "PromotionReceipt",
    "PulseGrabDecision",
    "RealityGateReceipt",
    "STYLES",
    "ScoreVector",
    "Strictness",
    "TransformationStep",
    "advisory_run_to_dict",
    "azatoth_generate",
    "default_pool_size",
    "derive_cache_key",
    "derive_inputer_cache_key",
    "evaluate_argument",
    "evaluate_pulse_grab",
    "generate_inputer",
    "generate_outputer",
    "generate_probes",
    "get_client",
    "inputer_result_to_dict",
    "nyahlothep_select",
    "outputer_result_to_dict",
    "render_inputer_prompt",
    "render_prompt",
    "run_advisory_wrapper",
    "to_human",
    "to_json_dict",
    "validate_inputer_payload",
    "validate_outputer_payload",
    "verify_pulse_grab_decision",
]
