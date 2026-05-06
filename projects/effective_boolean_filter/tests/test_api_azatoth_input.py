"""End-to-end API tests for POST /advisory/azatoth/input and the
``source=inputer`` path on POST /advisory/run.

Covers the failure policy at the HTTP layer:

* schema-valid happy path -> 200, full result shape
* invalid JSON / missing fields / unexpected fields / wrong types -> 422
* duplicate-only pool / insufficient unique candidates -> 422
* DisabledLLMClientError (provider configured, real adapter not in build) -> 503
* Pydantic body validation: bounds on count/pool_size, bad strictness, missing seed
* /advisory/run defaults to source=deterministic for backwards compatibility
* /advisory/run with source=inputer returns ``azatoth_inputer`` block and
  routes through the deterministic filter for selection
"""
from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

from fastapi.testclient import TestClient

from src.effective_boolean_filter.api import create_app
from src.effective_boolean_filter.llm_cache import LLMResponseCache
from src.effective_boolean_filter.llm_client import (
    DisabledLLMClientError,
    LLMClient,
    LLMRequest,
    LLMResponse,
)


def _candidate(idx: int, *, claim: str = "P", suffix: str = ""):
    return {
        "candidate_id": f"cand_{idx:03d}_test",
        "claim": claim,
        "argument": f"It is not the case that not {claim}. Therefore {claim}.{suffix}",
        "context": "logic",
        "strictness": "medium",
        "template": "clean_double_negation",
        "mutation_notes": f"variant {idx}",
    }


def _good_pool(n: int) -> str:
    return json.dumps({
        "azatoth_candidates": [
            _candidate(i, suffix=f" v{i}") for i in range(1, n + 1)
        ]
    })


class _ScriptedClient(LLMClient):
    def __init__(self, raw: str, *, provider: str = "scripted-fake", model: str = "scripted-fake-1") -> None:
        self._raw = raw
        self._provider = provider
        self._model = model
        self.calls: list[LLMRequest] = []

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(raw_text=self._raw, provider=self._provider, model=self._model)


class _DisabledClient(LLMClient):
    @property
    def provider(self) -> str:
        return "remote"

    @property
    def model(self) -> str:
        return "remote-1"

    def generate(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
        raise DisabledLLMClientError("remote provider is not available in this build")


# ----------------------------------------------------------------------
# /advisory/azatoth/input — happy path
# ----------------------------------------------------------------------

def test_input_endpoint_happy_path_full_shape():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 5, "strictness": "medium"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "mode", "provider", "model", "cache_key", "cached",
        "pool_size", "valid_count", "deduped_count", "azatoth_candidates",
    }
    assert body["mode"] == "contract_v0_inputer"
    assert body["provider"] == "fake-deterministic"
    assert body["cached"] is False
    assert body["pool_size"] >= 5
    assert body["valid_count"] >= 5
    assert body["deduped_count"] >= 5
    assert len(body["azatoth_candidates"]) == 5


def test_input_endpoint_respects_explicit_pool_size():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 4,
              "strictness": "medium", "pool_size": 24},
    )
    assert r.status_code == 200
    assert r.json()["pool_size"] == 24


def test_input_endpoint_cache_hit_through_api():
    cache = LLMResponseCache()
    c = TestClient(create_app(outputer_cache=cache))
    payload = {"seed": "P", "context": "logic", "count": 3, "strictness": "medium"}
    first = c.post("/advisory/azatoth/input", json=payload)
    second = c.post("/advisory/azatoth/input", json=payload)
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True


# ----------------------------------------------------------------------
# /advisory/azatoth/input — visible failures
# ----------------------------------------------------------------------

def test_input_endpoint_invalid_json_provider_returns_422():
    scripted = _ScriptedClient("not-json")
    c = TestClient(create_app(llm_client=scripted, outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 3, "strictness": "medium"},
    )
    assert r.status_code == 422
    assert "JSON" in r.json()["detail"] or "json" in r.json()["detail"].lower()


def test_input_endpoint_missing_field_returns_422():
    bad = _candidate(1)
    del bad["argument"]
    scripted = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    c = TestClient(create_app(llm_client=scripted, outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 1, "strictness": "medium"},
    )
    assert r.status_code == 422
    assert "missing required fields" in r.json()["detail"]


def test_input_endpoint_extra_field_returns_422():
    bad = _candidate(1)
    bad["score"] = 0.9
    scripted = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    c = TestClient(create_app(llm_client=scripted, outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 1, "strictness": "medium"},
    )
    assert r.status_code == 422
    assert "unexpected fields" in r.json()["detail"]


def test_input_endpoint_duplicate_only_pool_returns_422():
    dup_arg = "It is not the case that not P. Therefore P."
    pool = [
        {**_candidate(i), "argument": dup_arg, "claim": "P"} for i in range(1, 6)
    ]
    scripted = _ScriptedClient(json.dumps({"azatoth_candidates": pool}))
    c = TestClient(create_app(llm_client=scripted, outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 3, "strictness": "medium"},
    )
    assert r.status_code == 422
    assert "insufficient unique candidates" in r.json()["detail"]


def test_input_endpoint_disabled_provider_returns_503():
    c = TestClient(create_app(llm_client=_DisabledClient(), outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 3, "strictness": "medium"},
    )
    assert r.status_code == 503
    assert "not available" in r.json()["detail"]


# ----------------------------------------------------------------------
# /advisory/azatoth/input — Pydantic body validation
# ----------------------------------------------------------------------

@pytest.mark.parametrize("count", [0, -1, 21, 100])
def test_input_endpoint_count_out_of_range(count):
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": count, "strictness": "medium"},
    )
    assert r.status_code == 422


@pytest.mark.parametrize("pool_size", [0, -1, 81, 1000])
def test_input_endpoint_pool_size_out_of_range(pool_size):
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 5,
              "strictness": "medium", "pool_size": pool_size},
    )
    assert r.status_code == 422


def test_input_endpoint_bad_strictness():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 5, "strictness": "extreme"},
    )
    assert r.status_code == 422


def test_input_endpoint_seed_required():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"context": "logic", "count": 5, "strictness": "medium"},
    )
    assert r.status_code == 422


def test_input_endpoint_seed_over_max_length():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/azatoth/input",
        json={"seed": "x" * 4001, "context": "logic", "count": 5, "strictness": "medium"},
    )
    assert r.status_code == 422


# ----------------------------------------------------------------------
# /advisory/run — backwards-compat default + new source=inputer path
# ----------------------------------------------------------------------

def test_run_defaults_to_deterministic_for_backwards_compat():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/run",
        json={"seed": "P", "context": "logic", "count": 5, "strictness": "medium"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["azatoth_source"] == "deterministic"
    assert "azatoth_inputer" not in body


def test_run_with_source_inputer_routes_through_filter():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/run",
        json={
            "seed": "P", "context": "logic", "count": 5,
            "strictness": "medium", "source": "inputer",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["azatoth_source"] == "inputer"
    inputer = body["azatoth_inputer"]
    assert set(inputer) == {
        "mode", "provider", "model", "cache_key", "cached",
        "pool_size", "valid_count", "deduped_count",
    }
    assert inputer["mode"] == "contract_v0_inputer"
    # the deterministic filter still owns the verdict
    assert "selected_report" in body
    assert body["selected_report"]["effective_polarity"] in {
        "effective_yes", "effective_no", "unknown",
        "unstable", "untracked_shift", "contradiction",
    }


def test_run_with_inputer_invalid_json_returns_422():
    scripted = _ScriptedClient("not-json")
    c = TestClient(create_app(llm_client=scripted, outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/run",
        json={
            "seed": "P", "context": "logic", "count": 3,
            "strictness": "medium", "source": "inputer",
        },
    )
    assert r.status_code == 422


def test_run_with_inputer_disabled_provider_returns_503():
    c = TestClient(create_app(llm_client=_DisabledClient(), outputer_cache=LLMResponseCache()))
    r = c.post(
        "/advisory/run",
        json={
            "seed": "P", "context": "logic", "count": 3,
            "strictness": "medium", "source": "inputer",
        },
    )
    assert r.status_code == 503


def test_run_with_invalid_source_returns_422():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/run",
        json={
            "seed": "P", "context": "logic", "count": 3,
            "strictness": "medium", "source": "monkeys",
        },
    )
    assert r.status_code == 422


def test_run_with_inputer_pool_size_passes_through():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/run",
        json={
            "seed": "P", "context": "logic", "count": 3,
            "strictness": "medium", "source": "inputer", "pool_size": 24,
        },
    )
    assert r.status_code == 200
    assert r.json()["azatoth_inputer"]["pool_size"] == 24


# ----------------------------------------------------------------------
# read-only invariants
# ----------------------------------------------------------------------

def test_input_endpoint_does_not_corrupt_subsequent_run():
    """The inputer endpoint must not change the deterministic engine's
    behaviour on a follow-up evaluation."""
    c = TestClient(create_app())
    before = c.post(
        "/advisory/run",
        json={"seed": "P", "context": "logic", "count": 5, "strictness": "medium"},
    ).json()
    c.post(
        "/advisory/azatoth/input",
        json={"seed": "P", "context": "logic", "count": 5, "strictness": "medium"},
    )
    after = c.post(
        "/advisory/run",
        json={"seed": "P", "context": "logic", "count": 5, "strictness": "medium"},
    ).json()
    assert before["selected_report"]["effective_polarity"] == \
           after["selected_report"]["effective_polarity"]
    assert before["nyahlothep_selection"]["selected_candidate_id"] == \
           after["nyahlothep_selection"]["selected_candidate_id"]
