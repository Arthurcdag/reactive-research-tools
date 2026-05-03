from __future__ import annotations

import pytest

from src.effective_boolean_filter.advisory import (
    AdvisoryCandidate,
    CandidateEvaluation,
    advisory_candidate_to_dict,
    azatoth_generate,
    nyahlothep_select,
    run_advisory_wrapper,
)
from src.effective_boolean_filter.engine import evaluate_argument


def test_azatoth_generates_deterministic_candidate_shape():
    first = azatoth_generate(
        "X is true",
        context="science",
        count=4,
        strictness="medium",
    )
    second = azatoth_generate(
        "X is true",
        context="science",
        count=4,
        strictness="medium",
    )
    assert [advisory_candidate_to_dict(c) for c in first] == [
        advisory_candidate_to_dict(c) for c in second
    ]
    assert len(first) == 4
    assert first[0].candidate_id == "cand_001_clean_double_negation"
    assert first[0].claim
    assert first[0].argument
    assert first[0].context == "science"
    assert first[0].strictness == "medium"
    assert first[0].template
    assert first[0].mutation_notes


@pytest.mark.parametrize("bad_count", [0, 21])
def test_azatoth_rejects_out_of_bounds_count(bad_count):
    with pytest.raises(ValueError):
        azatoth_generate("P", count=bad_count)


def test_azatoth_never_returns_empty_candidates_at_max_count():
    candidates = azatoth_generate("   P.  ", count=20)
    assert len(candidates) == 20
    for candidate in candidates:
        assert candidate.claim
        assert candidate.argument
        assert candidate.candidate_id


def test_nyahlothep_selects_clean_double_negation_over_shifts():
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
        AdvisoryCandidate(
            candidate_id="scope",
            claim="X is true works in production",
            argument="X is true works in simulation. Therefore X is true works in production.",
            context="science",
            strictness="medium",
            template="simulation_scope_shift",
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
    assert selection.selected_candidate_id == "clean"
    assert selection.ranking[0]["candidate_id"] == "clean"


def test_run_advisory_wrapper_returns_contract_v0_selection_and_recipe():
    run = run_advisory_wrapper("X is true", context="science", count=8)
    assert run.mode == "contract_v0"
    assert len(run.azatoth_candidates) == 8
    assert run.nyahlothep_selection.selected_candidate_id == (
        "cand_001_clean_double_negation"
    )
    recipe = run.replication_recipe
    assert recipe["seed"] == "X is true"
    assert recipe["selected_candidate"]["candidate_id"] == (
        run.nyahlothep_selection.selected_candidate_id
    )
    assert recipe["template"] == "clean_double_negation"
