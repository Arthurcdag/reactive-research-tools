"""API tests for the Azatoth/Nyahlothep advisory wrapper."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


def _client():
    from fastapi.testclient import TestClient
    from src.effective_boolean_filter.api import create_app
    return TestClient(create_app())


def test_advisory_azatoth_endpoint_generates_candidates():
    r = _client().post(
        "/advisory/azatoth",
        json={"seed": "X is true", "context": "science", "count": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "contract_v0"
    assert len(body["azatoth_candidates"]) == 3
    candidate = body["azatoth_candidates"][0]
    for key in (
        "candidate_id",
        "claim",
        "argument",
        "context",
        "strictness",
        "template",
        "mutation_notes",
    ):
        assert key in candidate


def test_advisory_run_endpoint_selects_and_stores_report():
    client = _client()
    r = client.post(
        "/advisory/run",
        json={"seed": "X is true", "context": "science", "count": 8},
    )
    assert r.status_code == 200
    body = r.json()
    for key in (
        "id",
        "mode",
        "azatoth_candidates",
        "nyahlothep_selection",
        "selected_report",
        "replication_recipe",
        "trace",
        "gates",
    ):
        assert key in body
    assert body["mode"] == "contract_v0"
    assert body["trace"]["mode"] == "pipeline_trace_v0"
    assert body["trace"]["complete"] is True
    assert [stage["name"] for stage in body["trace"]["stages"]] == [
        "request_received",
        "candidates_generated",
        "candidates_evaluated",
        "promotion_decided",
        "reality_gate_checked",
        "selected_report_stored",
    ]
    assert body["gates"]["promotion"]["status"] == "pass"
    assert body["gates"]["reality"]["status"] == "pass"
    assert body["nyahlothep_selection"]["selected_candidate_id"] == (
        "cand_001_clean_double_negation"
    )
    selected_id = body["selected_report"]["id"]
    stored = client.get(f"/reports/{selected_id}")
    assert stored.status_code == 200
    assert stored.json() == body["selected_report"]


def test_advisory_nyahlothep_endpoint_selects_caller_candidates():
    r = _client().post(
        "/advisory/nyahlothep",
        json={
            "seed": "X is true",
            "candidates": [
                {
                    "candidate_id": "clean",
                    "claim": "X is true",
                    "argument": (
                        "It is not the case that not X is true. "
                        "Therefore X is true."
                    ),
                    "context": "science",
                    "strictness": "medium",
                    "template": "clean_double_negation",
                    "mutation_notes": "test candidate",
                },
                {
                    "candidate_id": "epistemic",
                    "claim": "X is true",
                    "argument": (
                        "There is no evidence against X is true. "
                        "Therefore X is true."
                    ),
                    "context": "science",
                    "strictness": "medium",
                    "template": "epistemic_absence",
                    "mutation_notes": "test candidate",
                },
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["trace"]["mode"] == "pipeline_trace_v0"
    assert body["trace"]["complete"] is True
    assert body["gates"]["promotion"]["status"] == "pass"
    assert body["gates"]["reality"]["status"] == "pass"
    assert body["nyahlothep_selection"]["selected_candidate_id"] == "clean"
    assert body["replication_recipe"]["selected_candidate"]["candidate_id"] == "clean"


@pytest.mark.parametrize("count", [0, 21])
def test_advisory_run_rejects_bad_count(count):
    r = _client().post("/advisory/run", json={"seed": "P", "count": count})
    assert r.status_code == 422


def test_advisory_run_rejects_seed_over_max_length():
    r = _client().post(
        "/advisory/run",
        json={"seed": "x" * 4001},
    )
    assert r.status_code == 422


def test_advisory_nyahlothep_rejects_empty_candidates():
    r = _client().post(
        "/advisory/nyahlothep",
        json={"seed": "P", "candidates": []},
    )
    assert r.status_code == 422


def test_advisory_nyahlothep_rejects_candidate_claim_over_max_length():
    r = _client().post(
        "/advisory/nyahlothep",
        json={
            "seed": "P",
            "candidates": [
                {
                    "candidate_id": "too-long",
                    "claim": "x" * 4001,
                    "argument": "P. Therefore P.",
                }
            ],
        },
    )
    assert r.status_code == 422
