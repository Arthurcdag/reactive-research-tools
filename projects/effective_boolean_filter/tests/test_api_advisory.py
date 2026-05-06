"""API tests for the Azatoth/Nyahlothep advisory wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


def _client():
    from fastapi.testclient import TestClient
    from src.effective_boolean_filter.api import create_app
    return TestClient(create_app())


def _ledger_client(path: Path):
    from fastapi.testclient import TestClient
    from src.effective_boolean_filter.api import create_app
    from src.effective_boolean_filter.advisory_ledger import FileAdvisoryLedger

    return TestClient(create_app(advisory_ledger=FileAdvisoryLedger(path)))


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
    assert body["ledger"] == {"enabled": False}
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
    assert body["ledger"] == {"enabled": False}
    assert body["nyahlothep_selection"]["selected_candidate_id"] == "clean"
    assert body["replication_recipe"]["selected_candidate"]["candidate_id"] == "clean"


def test_advisory_ledger_disabled_endpoints_return_503():
    client = _client()
    assert client.get("/advisory/ledger").status_code == 503
    assert client.get("/advisory/ledger/entry_000001").status_code == 503
    assert client.post("/advisory/ledger/entry_000001/replay").status_code == 503


def test_advisory_run_writes_file_ledger_and_replays(tmp_path: Path):
    client = _ledger_client(tmp_path / "ledger.jsonl")
    posted = client.post(
        "/advisory/run",
        json={"seed": "X is true", "context": "science", "count": 4},
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["ledger"]["enabled"] is True
    assert body["ledger"]["entry_id"] == "entry_000001"

    listed = client.get("/advisory/ledger")
    assert listed.status_code == 200
    entries = listed.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["entry_id"] == "entry_000001"
    assert entries[0]["run_id"] == body["id"]
    assert entries[0]["selected_report_id"] == body["selected_report"]["id"]

    fetched = client.get("/advisory/ledger/entry_000001")
    assert fetched.status_code == 200
    entry = fetched.json()
    assert entry["payload"]["request"]["seed"] == "X is true"
    assert entry["payload"]["response"]["id"] == body["id"]
    assert "ledger" not in entry["payload"]["response"]

    replay = client.post("/advisory/ledger/entry_000001/replay")
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["verified"] is True
    assert replay_body["chain_verified"] is True
    assert replay_body["replay_verified"] is True
    assert replay_body["mismatches"] == []


def test_advisory_nyahlothep_writes_file_ledger(tmp_path: Path):
    client = _ledger_client(tmp_path / "ledger.jsonl")
    posted = client.post(
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
                }
            ],
        },
    )
    assert posted.status_code == 200
    assert posted.json()["ledger"]["entry_id"] == "entry_000001"
    entry = client.get("/advisory/ledger/entry_000001").json()
    assert entry["endpoint"] == "/advisory/nyahlothep"
    assert entry["payload"]["request"]["candidates"][0]["candidate_id"] == "clean"


def test_advisory_ledger_missing_and_invalid_entries(tmp_path: Path):
    client = _ledger_client(tmp_path / "ledger.jsonl")
    assert client.get("/advisory/ledger/entry_000001").status_code == 404
    assert client.get("/advisory/ledger/../escape").status_code in (400, 404)


def test_advisory_ledger_corrupt_jsonl_returns_409(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("{bad json\n", encoding="utf-8")
    client = _ledger_client(path)
    assert client.get("/advisory/ledger").status_code == 409


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
