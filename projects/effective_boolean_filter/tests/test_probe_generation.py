"""Reactive probe generation (spec section 8 + 14 sprint 3)."""
from __future__ import annotations

from src.effective_boolean_filter import evaluate_argument


def test_at_least_five_probes_generated():
    r = evaluate_argument(
        claim="X is true",
        argument="There is no evidence against X, therefore X is true",
    )
    assert len(r.probes) >= 5


def test_epistemic_argument_gets_dependency_probe():
    r = evaluate_argument(
        claim="X is true",
        argument="There is no evidence against X, therefore X is true",
    )
    types = {p.type for p in r.probes}
    assert "remove_premise" in types or "ask_dependency" in types


def test_universal_claim_gets_counterexample_probe():
    r = evaluate_argument(
        claim="All swans are white",
        argument="Every swan I have seen is white. Therefore all swans are white.",
    )
    types = {p.type for p in r.probes}
    assert "ask_counterexample" in types


def test_falsifier_probe_always_present():
    r = evaluate_argument(claim="P", argument="P. Therefore P.")
    types = {p.type for p in r.probes}
    assert "ask_falsifier" in types


def test_scope_shift_triggers_implementation_probe():
    r = evaluate_argument(
        claim="It works in production",
        argument="It works in simulation. Therefore it works in production.",
    )
    types = {p.type for p in r.probes}
    assert "ask_implementation" in types or "weaken_premise" in types
