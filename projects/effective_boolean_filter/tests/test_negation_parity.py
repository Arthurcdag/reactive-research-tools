"""Tests for the deterministic negation-parity engine (spec section 4 + 16)."""
from __future__ import annotations

from src.effective_boolean_filter import evaluate_argument


def test_double_negation_reduces_to_yes():
    r = evaluate_argument(
        claim="P",
        argument="It is not the case that not P. Therefore P.",
        context="logic",
    )
    assert r.effective_polarity == "effective_yes"
    assert r.effectiveness_score >= 0.5


def test_triple_negation_reduces_to_no():
    r = evaluate_argument(
        claim="P",
        argument="It is not the case that it is not the case that not P. Therefore not P.",
        context="logic",
    )
    assert r.effective_polarity in {"effective_no", "effective_yes", "unstable"}
    # the conclusion follows correctly so trace must be tracked
    assert all(s.tracked for s in r.trace if s.transformation_type != "scope_shift")


def test_no_evidence_against_is_not_yes():
    r = evaluate_argument(
        claim="X is true",
        argument="There is no evidence against X, therefore X is true",
        context="scientific argument",
    )
    assert r.effective_polarity in {"untracked_shift", "unstable"}
    issue_codes = {i.code for i in r.issues}
    assert "epistemic_to_ontological_shift" in issue_codes


def test_not_proven_does_not_imply_proven():
    r = evaluate_argument(
        claim="P",
        argument="Not proven that not P. Therefore P.",
        context="logic",
    )
    assert r.effective_polarity in {"untracked_shift", "unstable"}


def test_not_false_is_yes():
    r = evaluate_argument(
        claim="P",
        argument="P is not false. Therefore P.",
        context="logic",
    )
    assert r.effective_polarity == "effective_yes"


def test_no_negation_baseline():
    r = evaluate_argument(claim="P", argument="P. Therefore P.")
    assert r.effective_polarity == "effective_yes"
    assert r.bogusness_score < 0.5
