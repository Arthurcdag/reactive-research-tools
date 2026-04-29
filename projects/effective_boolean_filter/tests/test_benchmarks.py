"""Regression test against the 50+ labeled benchmark examples.

Failing this test means a behavioural change happened — review the diff,
adjust either the engine or the example label, and only then update.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.effective_boolean_filter import evaluate_argument


BENCHMARK = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "examples.jsonl"
)


def _load() -> list[dict]:
    with BENCHMARK.open() as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.mark.parametrize("example", _load(), ids=lambda e: e["id"])
def test_polarity_in_expected_set(example):
    r = evaluate_argument(
        claim=example["claim"],
        argument=example["argument"],
    )
    expected = set(example["expected_polarity"])
    assert r.effective_polarity in expected, (
        f"{example['id']}: got {r.effective_polarity}, expected one of {expected}; "
        f"issues={[i.code for i in r.issues]}"
    )


@pytest.mark.parametrize("example", _load(), ids=lambda e: e["id"])
def test_expected_issues_present(example):
    r = evaluate_argument(
        claim=example["claim"],
        argument=example["argument"],
    )
    expected_issues = set(example.get("expected_issues", []))
    if not expected_issues:
        return
    detected = {i.code for i in r.issues}
    # we accept either an exact code match or a code that contains the expected substring
    for ec in expected_issues:
        assert any(ec in d or d in ec for d in detected), (
            f"{example['id']}: missing expected issue {ec!r}; got {detected}"
        )


def test_minimum_benchmark_size():
    examples = _load()
    assert len(examples) >= 50, f"need >=50 examples, found {len(examples)}"
