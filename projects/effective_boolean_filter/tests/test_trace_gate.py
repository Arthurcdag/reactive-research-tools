from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from src.effective_boolean_filter.advisory import (
    AdvisoryCandidate,
    CandidateEvaluation,
    advisory_candidate_to_dict,
    nyahlothep_select,
)
from src.effective_boolean_filter.engine import evaluate_argument
from src.effective_boolean_filter.report import to_json_dict
from src.effective_boolean_filter.trace_gate import (
    ORDERED_STAGES,
    PipelineInvariantError,
    PipelineTrace,
    check_reality_gate,
    decide_promotion,
    stable_evidence_hash,
    verify_promotion_receipt,
    verify_reality_gate_receipt,
)


def _sample_evaluated() -> tuple[list[dict], dict, dict]:
    candidates = [
        AdvisoryCandidate(
            candidate_id="clean",
            claim="X is true",
            argument="It is not the case that not X is true. Therefore X is true.",
            context="science",
            strictness="medium",
            template="clean_double_negation",
            mutation_notes="",
        ),
        AdvisoryCandidate(
            candidate_id="epistemic",
            claim="X is true",
            argument="There is no evidence against X is true. Therefore X is true.",
            context="science",
            strictness="medium",
            template="epistemic_absence",
            mutation_notes="",
        ),
    ]
    evaluated = [
        CandidateEvaluation(
            candidate=candidate,
            report=evaluate_argument(
                candidate.claim,
                candidate.argument,
                context=candidate.context,
                strictness=candidate.strictness,
            ),
            ordinal=idx,
        )
        for idx, candidate in enumerate(candidates)
    ]
    selection = nyahlothep_select(evaluated)
    evidence = [
        {
            "candidate": advisory_candidate_to_dict(ev.candidate),
            "report": to_json_dict(ev.report),
            "ordinal": ev.ordinal,
        }
        for ev in evaluated
    ]
    selection_dict = {
        "selected_candidate_id": selection.selected_candidate_id,
        "rank_reason": selection.rank_reason,
        "ranking": selection.ranking,
    }
    selected_report = next(
        item["report"]
        for item in evidence
        if item["candidate"]["candidate_id"] == selection.selected_candidate_id
    )
    return evidence, selection_dict, selected_report


def _trace_through_promotion(promotion_dict: dict) -> PipelineTrace:
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"seed": "X"})
    trace.record("candidates_generated", [{"candidate_id": "clean"}])
    trace.record("candidates_evaluated", [{"candidate_id": "clean", "id": "eval_x"}])
    trace.record("promotion_decided", promotion_dict)
    return trace


def test_trace_records_required_stages_in_order():
    trace = PipelineTrace("adv_test")
    for stage in ORDERED_STAGES:
        trace.record(stage, {"stage": stage})
    assert trace.complete is True
    assert trace.to_dict()["mode"] == "pipeline_trace_v0"
    assert [stage["name"] for stage in trace.to_dict()["stages"]] == list(ORDERED_STAGES)


def test_trace_rejects_duplicate_stage():
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"ok": True})
    with pytest.raises(PipelineInvariantError, match="stage order violation"):
        trace.record("request_received", {"again": True})


def test_trace_rejects_skipped_stage():
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"ok": True})
    with pytest.raises(PipelineInvariantError, match="stage order violation"):
        trace.record("candidates_evaluated", {"skipped": True})


def test_trace_rejects_out_of_order_stage():
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"ok": True})
    trace.record("candidates_generated", {"ok": True})
    with pytest.raises(PipelineInvariantError, match="stage order violation"):
        trace.record("request_received", {"late": True})


def test_trace_reports_missing_required_stage():
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"ok": True})
    with pytest.raises(PipelineInvariantError, match="trace is incomplete"):
        trace.require_complete()
    with pytest.raises(PipelineInvariantError, match="missing required"):
        trace.require_stage("promotion_decided")


def test_stable_evidence_hash_is_order_independent_for_dicts():
    first = stable_evidence_hash({"b": [2, 1], "a": {"x": "y"}})
    second = stable_evidence_hash({"a": {"x": "y"}, "b": [2, 1]})
    assert first == second


def test_promotion_gate_accepts_valid_evaluated_selection():
    evidence, selection, selected_report = _sample_evaluated()
    receipt = decide_promotion(
        evaluated=evidence,
        selection=selection,
        selected_report_id=selected_report["id"],
    )
    assert receipt.status == "pass"
    assert receipt.selected_candidate_id == "clean"
    assert receipt.selected_report_id == selected_report["id"]
    assert verify_promotion_receipt(receipt) is True


def test_promotion_gate_rejects_empty_evaluated_set():
    _, selection, selected_report = _sample_evaluated()
    with pytest.raises(PipelineInvariantError, match="evaluated candidates"):
        decide_promotion(
            evaluated=[],
            selection=selection,
            selected_report_id=selected_report["id"],
        )


def test_promotion_gate_rejects_unknown_selected_candidate():
    evidence, selection, selected_report = _sample_evaluated()
    bad = dict(selection)
    bad["selected_candidate_id"] = "missing"
    with pytest.raises(PipelineInvariantError, match="not evaluated"):
        decide_promotion(
            evaluated=evidence,
            selection=bad,
            selected_report_id=selected_report["id"],
        )


def test_promotion_gate_rejects_report_mismatch():
    evidence, selection, _selected_report = _sample_evaluated()
    with pytest.raises(PipelineInvariantError, match="report id"):
        decide_promotion(
            evaluated=evidence,
            selection=selection,
            selected_report_id="eval_someone_else",
        )


def test_promotion_gate_rejects_mutated_rank_evidence():
    evidence, selection, selected_report = _sample_evaluated()
    bad = deepcopy(selection)
    bad["ranking"][0]["rank_reason"] = "mutated"
    with pytest.raises(PipelineInvariantError, match="rank reason"):
        decide_promotion(
            evaluated=evidence,
            selection=bad,
            selected_report_id=selected_report["id"],
        )


def test_promotion_gate_rejects_mutated_report_summary():
    evidence, selection, selected_report = _sample_evaluated()
    bad = deepcopy(selection)
    bad["ranking"][0]["effectiveness_score"] = 0.0
    with pytest.raises(PipelineInvariantError, match="does not match"):
        decide_promotion(
            evaluated=evidence,
            selection=bad,
            selected_report_id=selected_report["id"],
        )


def test_reality_gate_accepts_complete_promotion_evidence():
    evidence, selection, selected_report = _sample_evaluated()
    promotion = decide_promotion(
        evaluated=evidence,
        selection=selection,
        selected_report_id=selected_report["id"],
    )
    trace = _trace_through_promotion(promotion.to_dict())
    reality = check_reality_gate(
        trace=trace,
        promotion=promotion,
        selected_report=selected_report,
    )
    assert reality.status == "pass"
    assert verify_reality_gate_receipt(
        reality,
        trace=trace,
        promotion=promotion,
        selected_report=selected_report,
    ) is True


def test_reality_gate_rejects_missing_promotion():
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"seed": "X"})
    with pytest.raises(PipelineInvariantError, match="promotion receipt"):
        check_reality_gate(trace=trace, promotion=None, selected_report={"id": "eval_x"})


def test_reality_gate_rejects_missing_evaluation_stage():
    evidence, selection, selected_report = _sample_evaluated()
    promotion = decide_promotion(
        evaluated=evidence,
        selection=selection,
        selected_report_id=selected_report["id"],
    )
    trace = PipelineTrace("adv_test")
    trace.record("request_received", {"seed": "X"})
    with pytest.raises(PipelineInvariantError, match="ordered stages"):
        check_reality_gate(
            trace=trace,
            promotion=promotion,
            selected_report=selected_report,
        )


def test_reality_gate_rejects_receipt_hash_mismatch():
    evidence, selection, selected_report = _sample_evaluated()
    promotion = decide_promotion(
        evaluated=evidence,
        selection=selection,
        selected_report_id=selected_report["id"],
    )
    bad_promotion = replace(promotion, evidence_hash="bad")
    trace = _trace_through_promotion(promotion.to_dict())
    with pytest.raises(PipelineInvariantError, match="hash mismatch"):
        check_reality_gate(
            trace=trace,
            promotion=bad_promotion,
            selected_report=selected_report,
        )
