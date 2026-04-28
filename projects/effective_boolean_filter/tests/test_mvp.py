from src.effective_boolean_filter.engine import evaluate_argument


def test_no_evidence_against_is_not_yes():
    r = evaluate_argument(
        claim="X is true",
        argument="There is no evidence against X, therefore X is true",
        context="scientific argument",
    )
    assert r["effective_polarity"] in {"untracked_shift", "unstable"}
    assert any("epistemic" in issue for issue in r["issues"])


def test_double_negation_cleaner():
    r = evaluate_argument(
        claim="P",
        argument="It is not the case that not P. Therefore P.",
        context="logic",
    )
    assert r["effectiveness_score"] >= 0.5
