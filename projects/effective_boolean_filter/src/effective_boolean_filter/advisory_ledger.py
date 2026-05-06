"""Append-only advisory ledger and deterministic replay verification."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Protocol

from .advisory import (
    AdvisoryCandidate,
    advisory_run_to_dict,
    run_nyahlothep_on_candidates,
)


_VALID_ENTRY_ID = re.compile(r"^entry_[0-9]{6}$")
_STRICTNESS_VALUES = {"low", "medium", "high"}


class LedgerError(RuntimeError):
    """Base class for advisory ledger failures."""


class LedgerDisabledError(LedgerError):
    """Raised when a caller tries to read/replay a disabled ledger."""


class LedgerCorruptionError(LedgerError):
    """Raised when the JSONL ledger cannot be parsed safely."""


class LedgerEntryNotFound(LedgerError):
    """Raised when an entry id is valid but absent."""


class LedgerValidationError(ValueError):
    """Raised when entry ids or stored replay payloads are malformed."""


@dataclass(frozen=True)
class ChainVerification:
    verified: bool
    mismatches: list[str]


class AdvisoryLedger(Protocol):
    enabled: bool

    def append(
        self,
        *,
        run_id: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    def list_summaries(self) -> list[dict[str, Any]]: ...
    def get(self, entry_id: str) -> dict[str, Any]: ...
    def replay(self, entry_id: str) -> dict[str, Any]: ...
    def verify_chain(self, *, through_entry_id: str | None = None) -> ChainVerification: ...


class NullAdvisoryLedger:
    """No-op ledger used unless EBF_ADVISORY_LEDGER is configured."""

    enabled = False

    def append(
        self,
        *,
        run_id: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {"enabled": False}

    def list_summaries(self) -> list[dict[str, Any]]:
        raise LedgerDisabledError("advisory ledger is not configured")

    def get(self, entry_id: str) -> dict[str, Any]:
        raise LedgerDisabledError("advisory ledger is not configured")

    def replay(self, entry_id: str) -> dict[str, Any]:
        raise LedgerDisabledError("advisory ledger is not configured")

    def verify_chain(self, *, through_entry_id: str | None = None) -> ChainVerification:
        raise LedgerDisabledError("advisory ledger is not configured")


class FileAdvisoryLedger:
    """Append-only JSONL advisory ledger."""

    enabled = True

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(
        self,
        *,
        run_id: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            entries = self._read_entries_unlocked()
            chain = _verify_entries(entries)
            if not chain.verified:
                raise LedgerCorruptionError(
                    "cannot append to advisory ledger with a broken hash chain"
                )
            sequence = len(entries) + 1
            previous_hash = entries[-1]["entry_hash"] if entries else None
            entry: dict[str, Any] = {
                "entry_id": f"entry_{sequence:06d}",
                "sequence": sequence,
                "created_at": _utc_now(),
                "run_id": run_id,
                "endpoint": endpoint,
                "previous_entry_hash": previous_hash,
                "payload": deepcopy(payload),
            }
            entry["entry_hash"] = compute_entry_hash(entry)
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(_canonical_json(entry))
                fh.write("\n")
            return {
                "enabled": True,
                "entry_id": entry["entry_id"],
                "sequence": entry["sequence"],
                "entry_hash": entry["entry_hash"],
            }

    def list_summaries(self) -> list[dict[str, Any]]:
        entries = self._read_entries()
        return [_summary_for_entry(entry) for entry in entries]

    def get(self, entry_id: str) -> dict[str, Any]:
        _check_entry_id(entry_id)
        entry = self._find_entry(entry_id)
        return deepcopy(entry)

    def replay(self, entry_id: str) -> dict[str, Any]:
        _check_entry_id(entry_id)
        entry = self._find_entry(entry_id)
        chain = self.verify_chain(through_entry_id=entry_id)
        replay = replay_advisory_entry(entry)
        mismatches = list(chain.mismatches) + replay["mismatches"]
        chain_verified = chain.verified
        replay_verified = replay["replay_verified"]
        return {
            "entry_id": entry_id,
            "run_id": entry.get("run_id"),
            "verified": chain_verified and replay_verified,
            "chain_verified": chain_verified,
            "replay_verified": replay_verified,
            "mismatches": mismatches,
            "stored_hashes": {
                "entry_hash": entry.get("entry_hash"),
                "previous_entry_hash": entry.get("previous_entry_hash"),
                "trace_hash": _trace_hash(entry),
                "promotion_hash": _promotion_hash(entry),
                "reality_hash": _reality_hash(entry),
            },
            "replayed": replay["replayed"],
        }

    def verify_chain(self, *, through_entry_id: str | None = None) -> ChainVerification:
        entries = self._read_entries()
        if through_entry_id is not None:
            _check_entry_id(through_entry_id)
            entries = _entries_through(entries, through_entry_id)
        return _verify_entries(entries)

    def _find_entry(self, entry_id: str) -> dict[str, Any]:
        entries = self._read_entries()
        for entry in entries:
            if entry.get("entry_id") == entry_id:
                return entry
        raise LedgerEntryNotFound(f"advisory ledger entry not found: {entry_id}")

    def _read_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_entries_unlocked()

    def _read_entries_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise LedgerCorruptionError(
                        f"malformed advisory ledger JSONL at line {line_no}"
                    ) from exc
                if not isinstance(value, dict):
                    raise LedgerCorruptionError(
                        f"advisory ledger line {line_no} is not an object"
                    )
                entries.append(value)
        return entries


def get_advisory_ledger(spec: str | None = None) -> AdvisoryLedger:
    """Resolve the advisory ledger from a spec string or environment."""
    if spec is None:
        spec = os.environ.get("EBF_ADVISORY_LEDGER", "")
    spec = spec.strip()
    if not spec or spec in {"none", "disabled"}:
        return NullAdvisoryLedger()
    if spec.startswith("file:"):
        path = spec[len("file:"):]
        if not path:
            raise ValueError(
                "file: ledger spec requires a path: 'file:/path/to/advisory-ledger.jsonl'"
            )
        return FileAdvisoryLedger(path)
    raise ValueError(f"unknown advisory ledger spec: {spec!r}")


def replay_advisory_entry(entry: dict[str, Any]) -> dict[str, Any]:
    payload = _required_dict(entry, "payload")
    request = _required_dict(payload, "request")
    stored_response = _required_dict(payload, "response")
    candidates = [
        _candidate_from_dict(candidate)
        for candidate in _required_list(stored_response, "azatoth_candidates")
    ]
    replayed_run = run_nyahlothep_on_candidates(
        seed=_string_or_empty(request.get("seed")),
        candidates=candidates,
    )
    replayed_response = advisory_run_to_dict(replayed_run)
    stored_normalized = _normalize_replay_response(stored_response)
    replayed_normalized = _normalize_replay_response(replayed_response)

    mismatches: list[str] = []
    _compare(
        mismatches,
        "run_id",
        stored_response.get("id"),
        replayed_response.get("id"),
    )
    _compare(
        mismatches,
        "selected_candidate_id",
        _selected_candidate_id(stored_response),
        _selected_candidate_id(replayed_response),
    )
    _compare(
        mismatches,
        "nyahlothep_selection.ranking",
        stored_normalized.get("nyahlothep_selection", {}).get("ranking"),
        replayed_normalized.get("nyahlothep_selection", {}).get("ranking"),
    )
    _compare(
        mismatches,
        "selected_report",
        stored_normalized.get("selected_report"),
        replayed_normalized.get("selected_report"),
    )
    _compare(
        mismatches,
        "trace",
        stored_normalized.get("trace"),
        replayed_normalized.get("trace"),
    )
    _compare(
        mismatches,
        "gates",
        stored_normalized.get("gates"),
        replayed_normalized.get("gates"),
    )

    return {
        "replay_verified": not mismatches,
        "mismatches": mismatches,
        "replayed": {
            "run_id": replayed_response.get("id"),
            "selected_candidate_id": _selected_candidate_id(replayed_response),
            "selected_report_id": _selected_report_id_from_response(replayed_response),
            "recommendation": replayed_response.get("selected_report", {}).get(
                "recommendation"
            ),
            "effectiveness_score": replayed_response.get("selected_report", {}).get(
                "effectiveness_score"
            ),
        },
    }


def compute_entry_hash(entry: dict[str, Any]) -> str:
    material = {key: value for key, value in entry.items() if key != "entry_hash"}
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def _normalize_replay_response(response: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(response)
    selected_report = out.get("selected_report")
    if isinstance(selected_report, dict):
        _normalize_report_ids(selected_report)
    trace = out.get("trace")
    if isinstance(trace, dict):
        for stage in trace.get("stages", []):
            if isinstance(stage, dict) and "evidence_hash" in stage:
                stage["evidence_hash"] = "<evidence_hash>"
    gates = out.get("gates")
    if isinstance(gates, dict):
        _normalize_gate_hashes(gates)
    return out


def _normalize_report_ids(report: dict[str, Any]) -> None:
    claim_ids: dict[str, str] = {}
    claims = report.get("claims")
    if isinstance(claims, list):
        for idx, claim in enumerate(claims, 1):
            if not isinstance(claim, dict):
                continue
            old_id = claim.get("id")
            placeholder = f"<claim_{idx}>"
            if isinstance(old_id, str):
                claim_ids[old_id] = placeholder
            claim["id"] = placeholder
    report["id"] = "<report_id>"
    for step in report.get("trace", []):
        if not isinstance(step, dict):
            continue
        for key in ("from_node", "to_node"):
            if isinstance(step.get(key), str):
                step[key] = claim_ids.get(step[key], "<claim_ref>")
    for issue in report.get("issues", []):
        if not isinstance(issue, dict):
            continue
        related = issue.get("related_node_ids")
        if isinstance(related, list):
            issue["related_node_ids"] = [
                claim_ids.get(item, "<claim_ref>") if isinstance(item, str) else item
                for item in related
            ]
    for probe in report.get("probes", []):
        if not isinstance(probe, dict):
            continue
        target = probe.get("targets_node_id")
        if isinstance(target, str):
            probe["targets_node_id"] = claim_ids.get(target, "<claim_ref>")
    contradiction = report.get("contradiction")
    if isinstance(contradiction, dict):
        pairs = contradiction.get("pairs")
        if isinstance(pairs, list):
            contradiction["pairs"] = [
                [
                    claim_ids.get(item, "<claim_ref>") if isinstance(item, str) else item
                    for item in pair
                ]
                if isinstance(pair, list)
                else pair
                for pair in pairs
            ]


def _normalize_gate_hashes(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key.endswith("_hash") or key == "evidence_hash":
                value[key] = "<evidence_hash>"
            elif key == "selected_report_id":
                value[key] = "<report_id>"
            else:
                _normalize_gate_hashes(item)
    elif isinstance(value, list):
        for item in value:
            _normalize_gate_hashes(item)


def _verify_entries(entries: list[dict[str, Any]]) -> ChainVerification:
    mismatches: list[str] = []
    previous_hash: str | None = None
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries, 1):
        entry_id = entry.get("entry_id")
        label = str(entry_id or f"line_{index}")
        if entry.get("sequence") != index:
            mismatches.append(f"{label}: sequence mismatch")
        if not isinstance(entry_id, str) or not _VALID_ENTRY_ID.match(entry_id):
            mismatches.append(f"{label}: invalid entry_id")
        elif entry_id in seen_ids:
            mismatches.append(f"{label}: duplicate entry_id")
        else:
            seen_ids.add(entry_id)
        if entry.get("previous_entry_hash") != previous_hash:
            mismatches.append(f"{label}: previous_entry_hash mismatch")
        actual_hash = compute_entry_hash(entry)
        if entry.get("entry_hash") != actual_hash:
            mismatches.append(f"{label}: entry_hash mismatch")
        previous_hash = entry.get("entry_hash")
    return ChainVerification(verified=not mismatches, mismatches=mismatches)


def _entries_through(entries: list[dict[str, Any]], entry_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        out.append(entry)
        if entry.get("entry_id") == entry_id:
            return out
    raise LedgerEntryNotFound(f"advisory ledger entry not found: {entry_id}")


def _candidate_from_dict(raw: Any) -> AdvisoryCandidate:
    if not isinstance(raw, dict):
        raise LedgerValidationError("stored candidate is not an object")
    strictness = _required_str(raw, "strictness")
    if strictness not in _STRICTNESS_VALUES:
        raise LedgerValidationError("stored candidate strictness is invalid")
    return AdvisoryCandidate(
        candidate_id=_required_str(raw, "candidate_id"),
        claim=_required_str(raw, "claim"),
        argument=_required_str(raw, "argument"),
        context=_string_or_empty(raw.get("context")),
        strictness=strictness,  # type: ignore[arg-type]
        template=_required_str(raw, "template"),
        mutation_notes=_string_or_empty(raw.get("mutation_notes")),
    )


def _summary_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": entry.get("entry_id"),
        "sequence": entry.get("sequence"),
        "created_at": entry.get("created_at"),
        "endpoint": entry.get("endpoint"),
        "run_id": entry.get("run_id"),
        "selected_report_id": _selected_report_id(entry),
        "entry_hash": entry.get("entry_hash"),
        "previous_entry_hash": entry.get("previous_entry_hash"),
    }


def _selected_report_id(entry: dict[str, Any]) -> str | None:
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None
    response = payload.get("response")
    if not isinstance(response, dict):
        return None
    return _selected_report_id_from_response(response)


def _selected_report_id_from_response(response: dict[str, Any]) -> str | None:
    selected_report = response.get("selected_report")
    if not isinstance(selected_report, dict):
        return None
    report_id = selected_report.get("id")
    return report_id if isinstance(report_id, str) else None


def _selected_candidate_id(response: dict[str, Any]) -> str | None:
    selection = response.get("nyahlothep_selection")
    if not isinstance(selection, dict):
        return None
    candidate_id = selection.get("selected_candidate_id")
    return candidate_id if isinstance(candidate_id, str) else None


def _trace_hash(entry: dict[str, Any]) -> str | None:
    response = _response_or_none(entry)
    if response is None:
        return None
    trace = response.get("trace")
    if not isinstance(trace, dict):
        return None
    return _short_hash(trace)


def _promotion_hash(entry: dict[str, Any]) -> str | None:
    response = _response_or_none(entry)
    if response is None:
        return None
    gates = response.get("gates")
    if not isinstance(gates, dict):
        return None
    promotion = gates.get("promotion")
    if not isinstance(promotion, dict):
        return None
    value = promotion.get("evidence_hash")
    return value if isinstance(value, str) else None


def _reality_hash(entry: dict[str, Any]) -> str | None:
    response = _response_or_none(entry)
    if response is None:
        return None
    gates = response.get("gates")
    if not isinstance(gates, dict):
        return None
    reality = gates.get("reality")
    if not isinstance(reality, dict):
        return None
    value = reality.get("evidence_hash")
    return value if isinstance(value, str) else None


def _response_or_none(entry: dict[str, Any]) -> dict[str, Any] | None:
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None
    response = payload.get("response")
    return response if isinstance(response, dict) else None


def _compare(mismatches: list[str], label: str, stored: Any, replayed: Any) -> None:
    if stored != replayed:
        mismatches.append(f"{label} mismatch")


def _check_entry_id(entry_id: str) -> None:
    if not _VALID_ENTRY_ID.match(entry_id):
        raise LedgerValidationError(f"invalid advisory ledger entry id: {entry_id!r}")


def _required_dict(item: dict[str, Any], key: str) -> dict[str, Any]:
    value = item.get(key)
    if not isinstance(value, dict):
        raise LedgerValidationError(f"stored ledger payload missing object: {key}")
    return value


def _required_list(item: dict[str, Any], key: str) -> list[Any]:
    value = item.get(key)
    if not isinstance(value, list):
        raise LedgerValidationError(f"stored ledger payload missing list: {key}")
    return value


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise LedgerValidationError(f"stored candidate missing string field: {key}")
    return value


def _string_or_empty(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _short_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()[:16]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
