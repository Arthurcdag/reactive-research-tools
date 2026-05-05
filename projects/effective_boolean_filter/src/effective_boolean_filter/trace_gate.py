"""Trace and gate primitives for advisory provenance.

This is a deliberately small "trace + gate" layer for the advisory wrapper.
It proves stage order and selected-report provenance. It does not decide
truth, execute actions, or change the deterministic filter's verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Literal, Sequence


TRACE_MODE = "pipeline_trace_v0"
PROMOTION_MODE = "promotion_gate_v0"
REALITY_MODE = "reality_gate_v0"

TraceStatus = Literal["pass", "fail"]
GateStatus = Literal["pass"]

ORDERED_STAGES: tuple[str, ...] = (
    "request_received",
    "candidates_generated",
    "candidates_evaluated",
    "promotion_decided",
    "reality_gate_checked",
    "selected_report_stored",
)
_STAGE_INDEX = {stage: idx for idx, stage in enumerate(ORDERED_STAGES)}


class PipelineInvariantError(RuntimeError):
    """Raised when advisory provenance cannot be proved."""


def stable_evidence_hash(value: object) -> str:
    """Return a deterministic short hash for JSON-serialisable evidence."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


@dataclass(frozen=True)
class TraceStage:
    name: str
    status: TraceStatus
    evidence_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "evidence_hash": self.evidence_hash,
        }


@dataclass
class PipelineTrace:
    run_id: str
    mode: str = TRACE_MODE
    stages: list[TraceStage] = field(default_factory=list)

    def record(
        self,
        name: str,
        evidence: object,
        *,
        status: TraceStatus = "pass",
    ) -> TraceStage:
        if name not in _STAGE_INDEX:
            raise PipelineInvariantError(f"unknown trace stage: {name!r}")
        if len(self.stages) >= len(ORDERED_STAGES):
            raise PipelineInvariantError("trace already complete")
        expected = ORDERED_STAGES[len(self.stages)]
        if name != expected:
            raise PipelineInvariantError(
                f"stage order violation: expected {expected!r}, got {name!r}"
            )
        stage = TraceStage(
            name=name,
            status=status,
            evidence_hash=stable_evidence_hash(evidence),
        )
        self.stages.append(stage)
        return stage

    def has_stage(self, name: str) -> bool:
        return any(stage.name == name for stage in self.stages)

    def require_stage(self, name: str) -> None:
        if not self.has_stage(name):
            raise PipelineInvariantError(f"missing required trace stage: {name}")

    def require_through(self, name: str) -> None:
        if name not in _STAGE_INDEX:
            raise PipelineInvariantError(f"unknown trace stage: {name!r}")
        needed = ORDERED_STAGES[: _STAGE_INDEX[name] + 1]
        actual = tuple(stage.name for stage in self.stages[: len(needed)])
        if actual != needed:
            raise PipelineInvariantError(
                f"trace does not include ordered stages through {name!r}"
            )

    @property
    def complete(self) -> bool:
        return tuple(stage.name for stage in self.stages) == ORDERED_STAGES

    def require_complete(self) -> None:
        if not self.complete:
            raise PipelineInvariantError("trace is incomplete")

    def stage_hash(self, name: str) -> str:
        for stage in self.stages:
            if stage.name == name:
                return stage.evidence_hash
        raise PipelineInvariantError(f"missing required trace stage: {name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "run_id": self.run_id,
            "stages": [stage.to_dict() for stage in self.stages],
            "complete": self.complete,
        }

    def to_dict_through(self, name: str) -> dict[str, Any]:
        self.require_through(name)
        idx = _STAGE_INDEX[name] + 1
        return {
            "mode": self.mode,
            "run_id": self.run_id,
            "stages": [stage.to_dict() for stage in self.stages[:idx]],
            "complete": idx == len(ORDERED_STAGES),
        }

    def evidence_hash(self) -> str:
        return stable_evidence_hash(self.to_dict())

    def evidence_hash_through(self, name: str) -> str:
        return stable_evidence_hash(self.to_dict_through(name))


@dataclass(frozen=True)
class PromotionReceipt:
    mode: str
    status: GateStatus
    selected_candidate_id: str
    selected_report_id: str
    rank_reason: str
    evaluation_hash: str
    selection_hash: str
    evidence_hash: str

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_report_id": self.selected_report_id,
            "rank_reason": self.rank_reason,
            "evaluation_hash": self.evaluation_hash,
            "selection_hash": self.selection_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        out = self.payload()
        out["evidence_hash"] = self.evidence_hash
        return out


@dataclass(frozen=True)
class RealityGateReceipt:
    mode: str
    status: GateStatus
    selected_report_id: str
    promotion_hash: str
    trace_hash: str
    selected_report_hash: str
    evidence_hash: str

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "selected_report_id": self.selected_report_id,
            "promotion_hash": self.promotion_hash,
            "trace_hash": self.trace_hash,
            "selected_report_hash": self.selected_report_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        out = self.payload()
        out["evidence_hash"] = self.evidence_hash
        return out


@dataclass(frozen=True)
class GateReceipts:
    promotion: PromotionReceipt
    reality: RealityGateReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "promotion": self.promotion.to_dict(),
            "reality": self.reality.to_dict(),
        }


def decide_promotion(
    *,
    evaluated: Sequence[dict[str, Any]],
    selection: dict[str, Any],
    selected_report_id: str,
) -> PromotionReceipt:
    """Validate that a selected candidate is backed by evaluated evidence."""
    if not evaluated:
        raise PipelineInvariantError("promotion requires evaluated candidates")

    by_id: dict[str, dict[str, Any]] = {}
    for item in evaluated:
        candidate = _candidate_from_evidence(item)
        candidate_id = _required_str(candidate, "candidate_id")
        if candidate_id in by_id:
            raise PipelineInvariantError(f"duplicate evaluated candidate: {candidate_id}")
        by_id[candidate_id] = item

    selected_candidate_id = _required_str(selection, "selected_candidate_id")
    rank_reason = _required_str(selection, "rank_reason")
    ranking = selection.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        raise PipelineInvariantError("promotion requires non-empty ranking evidence")
    if selected_candidate_id not in by_id:
        raise PipelineInvariantError("selected candidate was not evaluated")

    selected_eval = by_id[selected_candidate_id]
    selected_report = _report_from_evidence(selected_eval)
    actual_report_id = _required_str(selected_report, "id")
    if actual_report_id != selected_report_id:
        raise PipelineInvariantError("selected report id does not match evaluation")

    ranked_ids: set[str] = set()
    selected_row: dict[str, Any] | None = None
    for row in ranking:
        if not isinstance(row, dict):
            raise PipelineInvariantError("ranking rows must be objects")
        row_id = _required_str(row, "candidate_id")
        if row_id in ranked_ids:
            raise PipelineInvariantError(f"duplicate ranking candidate: {row_id}")
        ranked_ids.add(row_id)
        if row_id not in by_id:
            raise PipelineInvariantError("ranking references unevaluated candidate")
        _assert_ranking_matches_evaluation(row, by_id[row_id])
        if row_id == selected_candidate_id:
            selected_row = row

    if selected_row is None:
        raise PipelineInvariantError("selected candidate missing from ranking")
    if selected_row.get("rank") != 1:
        raise PipelineInvariantError("selected candidate is not rank 1")
    if selected_row.get("rank_reason") != rank_reason:
        raise PipelineInvariantError("selection rank reason does not match ranking")

    evaluation_hash = stable_evidence_hash(evaluated)
    selection_hash = stable_evidence_hash(selection)
    payload = {
        "mode": PROMOTION_MODE,
        "status": "pass",
        "selected_candidate_id": selected_candidate_id,
        "selected_report_id": selected_report_id,
        "rank_reason": rank_reason,
        "evaluation_hash": evaluation_hash,
        "selection_hash": selection_hash,
    }
    return PromotionReceipt(
        mode=PROMOTION_MODE,
        status="pass",
        selected_candidate_id=selected_candidate_id,
        selected_report_id=selected_report_id,
        rank_reason=rank_reason,
        evaluation_hash=evaluation_hash,
        selection_hash=selection_hash,
        evidence_hash=stable_evidence_hash(payload),
    )


def verify_promotion_receipt(receipt: PromotionReceipt | None) -> bool:
    if receipt is None:
        return False
    return receipt.evidence_hash == stable_evidence_hash(receipt.payload())


def check_reality_gate(
    *,
    trace: PipelineTrace,
    promotion: PromotionReceipt | None,
    selected_report: dict[str, Any],
) -> RealityGateReceipt:
    """Validate that a selected report may cross into the advisory response."""
    if promotion is None:
        raise PipelineInvariantError("reality gate requires a promotion receipt")
    if not verify_promotion_receipt(promotion):
        raise PipelineInvariantError("promotion receipt hash mismatch")

    trace.require_through("promotion_decided")
    if trace.stage_hash("promotion_decided") != stable_evidence_hash(promotion.to_dict()):
        raise PipelineInvariantError("trace promotion evidence does not match receipt")

    selected_report_id = _required_str(selected_report, "id")
    if selected_report_id != promotion.selected_report_id:
        raise PipelineInvariantError("selected report does not match promotion receipt")

    payload = {
        "mode": REALITY_MODE,
        "status": "pass",
        "selected_report_id": selected_report_id,
        "promotion_hash": promotion.evidence_hash,
        "trace_hash": trace.evidence_hash_through("promotion_decided"),
        "selected_report_hash": stable_evidence_hash(selected_report),
    }
    return RealityGateReceipt(
        mode=REALITY_MODE,
        status="pass",
        selected_report_id=selected_report_id,
        promotion_hash=payload["promotion_hash"],
        trace_hash=payload["trace_hash"],
        selected_report_hash=payload["selected_report_hash"],
        evidence_hash=stable_evidence_hash(payload),
    )


def verify_reality_gate_receipt(
    receipt: RealityGateReceipt | None,
    *,
    trace: PipelineTrace,
    promotion: PromotionReceipt,
    selected_report: dict[str, Any],
) -> bool:
    if receipt is None:
        return False
    expected = {
        "mode": REALITY_MODE,
        "status": "pass",
        "selected_report_id": selected_report.get("id"),
        "promotion_hash": promotion.evidence_hash,
        "trace_hash": trace.evidence_hash_through("promotion_decided"),
        "selected_report_hash": stable_evidence_hash(selected_report),
    }
    return receipt.evidence_hash == stable_evidence_hash(expected)


def _candidate_from_evidence(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("candidate")
    if not isinstance(candidate, dict):
        raise PipelineInvariantError("evaluated evidence missing candidate object")
    return candidate


def _report_from_evidence(item: dict[str, Any]) -> dict[str, Any]:
    report = item.get("report")
    if not isinstance(report, dict):
        raise PipelineInvariantError("evaluated evidence missing report object")
    return report


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise PipelineInvariantError(f"missing string field: {key}")
    return value


def _assert_ranking_matches_evaluation(
    row: dict[str, Any],
    evaluated: dict[str, Any],
) -> None:
    candidate = _candidate_from_evidence(evaluated)
    report = _report_from_evidence(evaluated)
    checks = {
        "template": candidate.get("template"),
        "effective_polarity": report.get("effective_polarity"),
        "recommendation": report.get("recommendation"),
        "effectiveness_score": report.get("effectiveness_score"),
        "bogusness_score": report.get("bogusness_score"),
        "issue_count": len(report.get("issues", [])),
        "error_count": sum(
            1 for issue in report.get("issues", [])
            if isinstance(issue, dict) and issue.get("severity") == "error"
        ),
    }
    for key, expected in checks.items():
        if row.get(key) != expected:
            raise PipelineInvariantError(
                f"ranking field {key!r} does not match evaluated report"
            )
