"""Advisory ledger and replay tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.effective_boolean_filter.advisory import (
    advisory_run_to_dict,
    run_advisory_wrapper,
)
from src.effective_boolean_filter.advisory_ledger import (
    FileAdvisoryLedger,
    LedgerCorruptionError,
    LedgerDisabledError,
    LedgerValidationError,
    NullAdvisoryLedger,
    compute_entry_hash,
    get_advisory_ledger,
)


def _payload(seed: str = "X is true", count: int = 4) -> dict:
    run = run_advisory_wrapper(
        seed,
        context="science",
        count=count,
        strictness="medium",
    )
    response = advisory_run_to_dict(run)
    response["azatoth_source"] = "deterministic"
    return {
        "request": {
            "seed": seed,
            "context": "science",
            "count": count,
            "strictness": "medium",
            "source": "deterministic",
            "pool_size": None,
        },
        "response": response,
    }


def _read_first_entry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def _write_entries(path: Path, entries: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )


def test_null_ledger_append_is_disabled_metadata():
    ledger = NullAdvisoryLedger()
    assert ledger.append(run_id="adv_x", endpoint="/advisory/run", payload={}) == {
        "enabled": False
    }
    with pytest.raises(LedgerDisabledError):
        ledger.list_summaries()


def test_get_advisory_ledger_resolves_disabled_and_file(tmp_path: Path):
    assert isinstance(get_advisory_ledger(""), NullAdvisoryLedger)
    ledger = get_advisory_ledger(f"file:{tmp_path / 'ledger.jsonl'}")
    assert isinstance(ledger, FileAdvisoryLedger)


def test_file_ledger_append_list_and_get_round_trip(tmp_path: Path):
    ledger = FileAdvisoryLedger(tmp_path / "ledger.jsonl")
    payload = _payload()
    meta = ledger.append(
        run_id=payload["response"]["id"],
        endpoint="/advisory/run",
        payload=payload,
    )
    assert meta["enabled"] is True
    assert meta["entry_id"] == "entry_000001"
    assert meta["sequence"] == 1

    summaries = ledger.list_summaries()
    assert summaries == [
        {
            "entry_id": "entry_000001",
            "sequence": 1,
            "created_at": summaries[0]["created_at"],
            "endpoint": "/advisory/run",
            "run_id": payload["response"]["id"],
            "selected_report_id": payload["response"]["selected_report"]["id"],
            "entry_hash": meta["entry_hash"],
            "previous_entry_hash": None,
        }
    ]
    stored = ledger.get("entry_000001")
    assert stored["payload"] == payload
    assert stored["entry_hash"] == compute_entry_hash(stored)


def test_file_ledger_append_deep_copies_payload(tmp_path: Path):
    ledger = FileAdvisoryLedger(tmp_path / "ledger.jsonl")
    payload = _payload()
    ledger.append(
        run_id=payload["response"]["id"],
        endpoint="/advisory/run",
        payload=payload,
    )
    payload["response"]["azatoth_candidates"][0]["argument"] = "mutated"
    assert ledger.get("entry_000001")["payload"] != payload


def test_file_ledger_chain_verification_detects_entry_hash_mismatch(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = FileAdvisoryLedger(path)
    payload = _payload()
    ledger.append(
        run_id=payload["response"]["id"],
        endpoint="/advisory/run",
        payload=payload,
    )
    entry = _read_first_entry(path)
    entry["entry_hash"] = "bad"
    _write_entries(path, [entry])
    chain = ledger.verify_chain()
    assert chain.verified is False
    assert chain.mismatches == ["entry_000001: entry_hash mismatch"]


def test_file_ledger_chain_verification_detects_previous_hash_mismatch(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = FileAdvisoryLedger(path)
    first = _payload("X is true")
    second = _payload("Y is true")
    ledger.append(
        run_id=first["response"]["id"],
        endpoint="/advisory/run",
        payload=first,
    )
    ledger.append(
        run_id=second["response"]["id"],
        endpoint="/advisory/run",
        payload=second,
    )
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    entries[1]["previous_entry_hash"] = "wrong"
    entries[1]["entry_hash"] = compute_entry_hash(entries[1])
    _write_entries(path, entries)
    chain = ledger.verify_chain()
    assert chain.verified is False
    assert chain.mismatches == ["entry_000002: previous_entry_hash mismatch"]


def test_file_ledger_rejects_corrupt_jsonl(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("{bad json\n", encoding="utf-8")
    ledger = FileAdvisoryLedger(path)
    with pytest.raises(LedgerCorruptionError):
        ledger.list_summaries()


def test_file_ledger_rejects_invalid_entry_id(tmp_path: Path):
    ledger = FileAdvisoryLedger(tmp_path / "ledger.jsonl")
    with pytest.raises(LedgerValidationError):
        ledger.get("../escape")


def test_file_ledger_replay_success(tmp_path: Path):
    ledger = FileAdvisoryLedger(tmp_path / "ledger.jsonl")
    payload = _payload()
    meta = ledger.append(
        run_id=payload["response"]["id"],
        endpoint="/advisory/run",
        payload=payload,
    )
    replay = ledger.replay(meta["entry_id"])
    assert replay["verified"] is True
    assert replay["chain_verified"] is True
    assert replay["replay_verified"] is True
    assert replay["mismatches"] == []
    assert replay["replayed"]["selected_candidate_id"] == (
        payload["response"]["nyahlothep_selection"]["selected_candidate_id"]
    )
    assert replay["replayed"]["recommendation"] == (
        payload["response"]["selected_report"]["recommendation"]
    )


def test_file_ledger_replay_detects_candidate_tamper(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = FileAdvisoryLedger(path)
    payload = _payload()
    ledger.append(
        run_id=payload["response"]["id"],
        endpoint="/advisory/run",
        payload=payload,
    )
    entry = _read_first_entry(path)
    tampered = deepcopy(entry)
    tampered["payload"]["response"]["azatoth_candidates"][0]["argument"] = (
        "There is no evidence against Y is true. Therefore Y is true."
    )
    _write_entries(path, [tampered])
    replay = ledger.replay("entry_000001")
    assert replay["verified"] is False
    assert "entry_000001: entry_hash mismatch" in replay["mismatches"]
    assert "selected_report mismatch" in replay["mismatches"]


def test_file_ledger_replay_rejects_malformed_payload(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ledger = FileAdvisoryLedger(path)
    payload = _payload()
    ledger.append(
        run_id=payload["response"]["id"],
        endpoint="/advisory/run",
        payload=payload,
    )
    entry = _read_first_entry(path)
    del entry["payload"]["response"]["azatoth_candidates"]
    entry["entry_hash"] = compute_entry_hash(entry)
    _write_entries(path, [entry])
    with pytest.raises(LedgerValidationError):
        ledger.replay("entry_000001")
