"""Contradiction containment (spec section 7 + 16)."""
from __future__ import annotations

from src.effective_boolean_filter import evaluate_argument


def test_contained_contradiction_does_not_explode():
    r = evaluate_argument(
        claim="The model is useful in restricted context B",
        argument=(
            "The model failed in context A. The model works in context B. "
            "Therefore the model is useful in restricted context B."
        ),
        context="ml",
    )
    # not auto-discarded; status should be a containable kind
    assert r.contradiction.status in {
        "scope_resolved",
        "definition_resolved",
        "contained",
    }
    # conclusion is about B only — not breaking
    assert r.contradiction.status != "breaking"


def test_breaking_contradiction_isolates():
    r = evaluate_argument(
        claim="P holds",
        argument="P. Not P. Therefore P holds.",
        context="logic",
    )
    # whatever the exact label, polarity must reflect instability
    assert r.effective_polarity in {"contradiction", "unstable", "untracked_shift"}
    assert r.contradiction.status != "none"


def test_temporal_resolution():
    r = evaluate_argument(
        claim="The service is up now",
        argument=(
            "Yesterday the service was down. Today the service is up. "
            "Therefore the service is up now."
        ),
        context="ops",
    )
    # temporal contradiction resolves; conclusion stays usable
    assert r.contradiction.status in {"temporal_resolved", "scope_resolved", "contained", "none"}
    assert r.effective_polarity in {"effective_yes", "unstable"}


def test_no_contradiction_when_compatible():
    r = evaluate_argument(
        claim="The function returns 1",
        argument="f returns 1 on input a. f returns 1 on input b. Therefore the function returns 1.",
        context="code",
    )
    assert r.contradiction.status == "none"
