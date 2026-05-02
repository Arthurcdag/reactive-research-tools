"""Storage backend tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.effective_boolean_filter.storage import (
    FileStore,
    InMemoryStore,
    get_store,
)


SAMPLE = {"id": "eval_abc123", "effective_polarity": "effective_yes", "score": 0.9}


def test_in_memory_round_trip():
    s = InMemoryStore()
    s.put(SAMPLE["id"], SAMPLE)
    assert s.get(SAMPLE["id"]) == SAMPLE
    assert SAMPLE["id"] in s
    assert s.list_ids() == [SAMPLE["id"]]


def test_in_memory_missing_returns_none():
    s = InMemoryStore()
    assert s.get("eval_missing") is None
    assert "eval_missing" not in s


def test_file_store_round_trip(tmp_path: Path):
    s = FileStore(tmp_path)
    s.put(SAMPLE["id"], SAMPLE)
    assert s.get(SAMPLE["id"]) == SAMPLE
    # second instance reads the same data — proves persistence
    s2 = FileStore(tmp_path)
    assert s2.get(SAMPLE["id"]) == SAMPLE
    assert SAMPLE["id"] in s2


def test_file_store_creates_root(tmp_path: Path):
    target = tmp_path / "nested" / "dir"
    s = FileStore(target)
    assert target.is_dir()
    s.put("eval_x", {"id": "eval_x"})
    assert (target / "eval_x.json").exists()


def test_file_store_atomic_replace(tmp_path: Path):
    s = FileStore(tmp_path)
    s.put("eval_a", {"v": 1})
    s.put("eval_a", {"v": 2})
    assert s.get("eval_a") == {"v": 2}
    # no leftover tempfiles starting with "."
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_file_store_list_ids_skips_non_json(tmp_path: Path):
    s = FileStore(tmp_path)
    s.put("eval_one", {})
    (tmp_path / "not_a_report.txt").write_text("ignore me")
    (tmp_path / ".hidden.json").write_text("{}")
    assert s.list_ids() == ["eval_one"]


def test_invalid_id_rejected(tmp_path: Path):
    for bad in ("../escape", "with space", "", "a/b", "x" * 200):
        with pytest.raises(ValueError):
            InMemoryStore().put(bad, {})
        with pytest.raises(ValueError):
            FileStore(tmp_path).put(bad, {})


def test_invalid_id_get_returns_falsy(tmp_path: Path):
    # __contains__ must be safe for malformed ids — never raises
    assert "../escape" not in InMemoryStore()
    assert "../escape" not in FileStore(tmp_path)


def test_get_store_default_is_memory(monkeypatch):
    monkeypatch.delenv("EBF_REPORT_STORE", raising=False)
    s = get_store()
    assert isinstance(s, InMemoryStore)


def test_get_store_memory_explicit():
    assert isinstance(get_store("memory"), InMemoryStore)


def test_get_store_file_spec(tmp_path: Path):
    s = get_store(f"file:{tmp_path}")
    assert isinstance(s, FileStore)
    s.put("eval_y", {"k": 1})
    assert (tmp_path / "eval_y.json").exists()


def test_get_store_file_spec_requires_path():
    with pytest.raises(ValueError):
        get_store("file:")


def test_get_store_unknown_spec_raises():
    with pytest.raises(ValueError):
        get_store("redis://localhost")


def test_get_store_env_var(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EBF_REPORT_STORE", f"file:{tmp_path}")
    s = get_store()
    assert isinstance(s, FileStore)
    s.put("eval_z", {})
    assert (tmp_path / "eval_z.json").exists()


def test_file_store_preserves_unicode(tmp_path: Path):
    s = FileStore(tmp_path)
    payload = {"id": "eval_u", "claim": "テスト"}  # "テスト"
    s.put("eval_u", payload)
    raw = (tmp_path / "eval_u.json").read_text(encoding="utf-8")
    # ensure_ascii=False means the unicode chars are stored literally
    assert "テ" in raw
    assert s.get("eval_u") == payload
