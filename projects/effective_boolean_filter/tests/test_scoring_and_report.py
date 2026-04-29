"""Score vector, recommendation and report shape."""
from __future__ import annotations

from src.effective_boolean_filter import evaluate_argument, to_human, to_json_dict


def test_score_breakdown_has_all_fields():
    r = evaluate_argument(claim="P", argument="Not not P. Therefore P.")
    sv = r.score_vector
    for f in (
        "negation_consistency",
        "scope_preservation",
        "definition_stability",
        "context_fit",
        "contradiction_containment",
        "reactive_performance",
        "testability",
        "implementation_relevance",
    ):
        v = getattr(sv, f)
        assert 0.0 <= v <= 1.0


def test_bogusness_high_for_epistemic_proof():
    r = evaluate_argument(
        claim="X is proven",
        argument="No one can disprove X, therefore X is proven.",
    )
    assert r.bogusness_score >= 0.5
    assert r.recommendation in {"reject", "needs_testing"}


def test_recommendation_accept_for_clean_argument():
    r = evaluate_argument(
        claim="P",
        argument="It is not the case that not P. Therefore P.",
    )
    assert r.recommendation in {"accept", "accept_with_caveats"}


def test_to_json_dict_shape():
    r = evaluate_argument(claim="P", argument="P. Therefore P.")
    d = to_json_dict(r)
    for key in (
        "id",
        "effective_polarity",
        "effectiveness_score",
        "bogusness_score",
        "score_vector",
        "claims",
        "trace",
        "issues",
        "probes",
        "contradiction",
        "recommendation",
    ):
        assert key in d


def test_to_human_renders_string():
    r = evaluate_argument(claim="P", argument="P. Therefore P.")
    out = to_human(r)
    assert "Effective polarity" in out
    assert "Score breakdown" in out
    assert "Recommended probes" in out


def test_score_reasons_recorded():
    r = evaluate_argument(
        claim="X is true",
        argument="There is no evidence against X, therefore X is true",
    )
    reasons = r.score_vector.reasons
    # at least one penalty must have a reason string
    assert any(reasons.get(f) for f in (
        "negation_consistency", "scope_preservation", "definition_stability",
        "context_fit", "contradiction_containment", "reactive_performance",
        "testability", "implementation_relevance",
    ))
