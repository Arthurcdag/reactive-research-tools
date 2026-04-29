"""Scope shift detection (spec section 4.3 + 16)."""
from __future__ import annotations

from src.effective_boolean_filter import evaluate_argument


def test_legal_to_physical_shift():
    r = evaluate_argument(
        claim="It is physically possible",
        argument="It is not legally impossible. Therefore it is physically possible.",
        context="modal",
    )
    codes = {i.code for i in r.issues}
    assert any("legal_to_physical" in c for c in codes)
    assert r.effective_polarity in {"unstable", "untracked_shift"}


def test_simulation_to_production_shift():
    r = evaluate_argument(
        claim="The system works in production",
        argument="It works in simulation. Therefore it works in production.",
        context="engineering",
    )
    codes = {i.code for i in r.issues}
    assert any("simulation_to_production" in c for c in codes)
    assert r.effective_polarity in {"unstable", "untracked_shift"}


def test_simulation_to_production_with_bridge():
    r = evaluate_argument(
        claim="The system works in production",
        argument=(
            "It works in simulation. The simulation has been validated against "
            "production traces. Therefore it works in production."
        ),
        context="engineering",
    )
    codes = {i.code for i in r.issues}
    assert not any("simulation_to_production" in c for c in codes)


def test_restricted_scope_is_clean():
    r = evaluate_argument(
        claim="The model is accurate on dataset D",
        argument="We achieved 0.92 F1 on dataset D. Therefore the model is accurate on dataset D.",
        context="ml",
    )
    assert r.effective_polarity == "effective_yes"
