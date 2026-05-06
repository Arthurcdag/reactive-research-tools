"""Unit tests for the Nyahlothep outputer.

Covers the failure policy from the developer brief:

* invalid JSON -> visible OutputerValidationError
* schema mismatch (missing/extra/wrong-type fields) -> visible error
* source_report_id mismatch -> visible error
* cache hit avoids second client call
* outputer never mutates the input selected_report or recipe
* unknown style / malformed inputs -> visible error
* DisabledLLMClientError surfaces from get_client when env asks for an
  unsupported or misconfigured provider
"""
from __future__ import annotations

import copy
import json

import pytest

from src.effective_boolean_filter.llm_cache import LLMResponseCache
from src.effective_boolean_filter.llm_client import (
    DeterministicFakeClient,
    DisabledLLMClientError,
    LLMRequest,
    LLMResponse,
    LLMClient,
    get_client,
)
from src.effective_boolean_filter.llm_outputer import (
    MODE,
    OutputerResult,
    OutputerValidationError,
    generate_outputer,
    outputer_result_to_dict,
    validate_outputer_payload,
)
from src.effective_boolean_filter.llm_prompts import PROMPT_VERSION, STYLES


SELECTED = {
    "id": "eval_test_001",
    "effective_polarity": "effective_yes",
    "recommendation": "accept",
    "effectiveness_score": 0.875,
    "bogusness_score": 0.125,
    "issues": [],
    "trace": [],
    "score_vector": {},
}
RECIPE = {
    "seed": "P",
    "selected_candidate": {"candidate_id": "cand_001_clean_double_negation"},
    "rank_reason": "clean_double_negation: accept with 0.875 effectiveness",
}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _good_payload(report_id: str = "eval_test_001") -> dict:
    return {
        "summary": "Engine accepted; verdict is effective_yes.",
        "why_selected": "rank_reason indicates a clean trace.",
        "replication_steps": ["Re-run the seed", "Inspect the verdict"],
        "caveats": ["Heuristic only"],
        "source_report_id": report_id,
    }


class _CountingFake(LLMClient):
    """Fake client that returns a scripted JSON string and counts calls."""

    def __init__(self, raw: str, *, provider: str = "test-fake", model: str = "test-fake-1") -> None:
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


# ----------------------------------------------------------------------
# happy path
# ----------------------------------------------------------------------

def test_happy_path_returns_validated_output_for_each_style():
    cache = LLMResponseCache()
    for style in STYLES:
        client = DeterministicFakeClient()
        r = generate_outputer(
            selected_report=SELECTED,
            replication_recipe=RECIPE,
            style=style,
            client=client,
            cache=cache,
        )
        assert r.mode == MODE
        assert r.provider == "fake-deterministic"
        assert r.cached is False
        assert r.validated_output["source_report_id"] == SELECTED["id"]
        for required in ("summary", "why_selected", "replication_steps", "caveats", "source_report_id"):
            assert required in r.validated_output


def test_to_dict_shape_matches_spec():
    client = DeterministicFakeClient()
    cache = LLMResponseCache()
    r = generate_outputer(
        selected_report=SELECTED,
        replication_recipe=RECIPE,
        style="brief",
        client=client,
        cache=cache,
    )
    d = outputer_result_to_dict(r)
    assert set(d) == {"mode", "provider", "model", "cache_key", "cached", "validated_output"}
    assert set(d["validated_output"]) == {
        "summary", "why_selected", "replication_steps", "caveats", "source_report_id",
    }


# ----------------------------------------------------------------------
# cache
# ----------------------------------------------------------------------

def test_cache_hit_avoids_second_provider_call():
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(_good_payload()))
    first = generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    second = generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    assert first.cached is False
    assert second.cached is True
    assert len(client.calls) == 1
    assert first.cache_key == second.cache_key
    # validated_output should match across calls
    assert first.validated_output == second.validated_output


def test_cache_distinguishes_styles():
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(_good_payload()))
    generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="technical", client=client, cache=cache,
    )
    assert len(client.calls) == 2  # different cache keys, no hit


def test_cache_distinguishes_reports():
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(_good_payload()))
    generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    other = {**SELECTED, "id": "eval_other_999"}
    other_payload = json.dumps(_good_payload(report_id="eval_other_999"))
    client2 = _CountingFake(other_payload)
    generate_outputer(
        selected_report=other, replication_recipe=RECIPE,
        style="brief", client=client2, cache=cache,
    )
    assert len(client.calls) == 1
    assert len(client2.calls) == 1


def test_cache_key_includes_prompt_version():
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(_good_payload()))
    r = generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    assert PROMPT_VERSION in r.cache_key
    assert client.provider in r.cache_key


# ----------------------------------------------------------------------
# validation failures must be visible
# ----------------------------------------------------------------------

def test_invalid_json_raises_visible_error():
    cache = LLMResponseCache()
    client = _CountingFake("not-json-at-all")
    with pytest.raises(OutputerValidationError) as exc:
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )
    assert "not valid JSON" in str(exc.value)


def test_missing_required_field_raises():
    payload = _good_payload()
    del payload["why_selected"]
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(payload))
    with pytest.raises(OutputerValidationError) as exc:
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )
    assert "missing required fields" in str(exc.value)


def test_extra_unexpected_field_raises():
    payload = _good_payload()
    payload["score"] = 0.9   # not in schema
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(payload))
    with pytest.raises(OutputerValidationError) as exc:
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )
    assert "unexpected fields" in str(exc.value)


def test_wrong_type_field_raises():
    payload = _good_payload()
    payload["replication_steps"] = "single string instead of list"
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(payload))
    with pytest.raises(OutputerValidationError):
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )


def test_empty_replication_steps_raises():
    payload = _good_payload()
    payload["replication_steps"] = []
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(payload))
    with pytest.raises(OutputerValidationError):
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )


def test_empty_summary_raises():
    payload = _good_payload()
    payload["summary"] = "   "
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(payload))
    with pytest.raises(OutputerValidationError):
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )


def test_source_report_id_mismatch_raises():
    payload = _good_payload(report_id="eval_someone_elses_report")
    cache = LLMResponseCache()
    client = _CountingFake(json.dumps(payload))
    with pytest.raises(OutputerValidationError) as exc:
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )
    assert "source_report_id mismatch" in str(exc.value)


def test_invalid_payload_does_not_get_cached():
    cache = LLMResponseCache()
    bad = _good_payload()
    del bad["caveats"]
    client = _CountingFake(json.dumps(bad))
    with pytest.raises(OutputerValidationError):
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )
    assert len(cache) == 0


def test_unknown_style_raises():
    cache = LLMResponseCache()
    client = DeterministicFakeClient()
    with pytest.raises(OutputerValidationError):
        generate_outputer(
            selected_report=SELECTED, replication_recipe=RECIPE,
            style="extreme",  # type: ignore[arg-type]
            client=client, cache=cache,
        )


def test_selected_report_without_id_raises():
    cache = LLMResponseCache()
    client = DeterministicFakeClient()
    with pytest.raises(OutputerValidationError):
        generate_outputer(
            selected_report={"effective_polarity": "effective_yes"},
            replication_recipe=RECIPE,
            style="brief", client=client, cache=cache,
        )


# ----------------------------------------------------------------------
# no-mutation invariant
# ----------------------------------------------------------------------

def test_outputer_never_mutates_selected_report_or_recipe():
    selected = copy.deepcopy(SELECTED)
    recipe = copy.deepcopy(RECIPE)
    cache = LLMResponseCache()
    client = DeterministicFakeClient()
    generate_outputer(
        selected_report=selected, replication_recipe=recipe,
        style="brief", client=client, cache=cache,
    )
    assert selected == SELECTED, "selected_report was mutated"
    assert recipe == RECIPE, "replication_recipe was mutated"


def test_validated_output_dict_is_a_copy_per_call():
    """Mutating one returned dict must not affect the cached entry."""
    cache = LLMResponseCache()
    client = DeterministicFakeClient()
    r1 = generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    r1.validated_output["summary"] = "POISONED"
    r1.validated_output["replication_steps"][0] = "POISONED STEP"
    r1.validated_output["caveats"].append("POISONED CAVEAT")
    r2 = generate_outputer(
        selected_report=SELECTED, replication_recipe=RECIPE,
        style="brief", client=client, cache=cache,
    )
    assert r2.cached is True
    assert r2.validated_output["summary"] != "POISONED"
    assert r2.validated_output["replication_steps"][0] != "POISONED STEP"
    assert "POISONED CAVEAT" not in r2.validated_output["caveats"]


# ----------------------------------------------------------------------
# direct schema-validator unit tests
# ----------------------------------------------------------------------

def test_validate_payload_must_be_dict():
    with pytest.raises(OutputerValidationError):
        validate_outputer_payload(["not", "a", "dict"], expected_report_id="x")


def test_validate_payload_caveats_can_be_empty_list():
    payload = _good_payload()
    payload["caveats"] = []
    out = validate_outputer_payload(payload, expected_report_id="eval_test_001")
    assert out["caveats"] == []


def test_validate_payload_caveats_must_be_strings():
    payload = _good_payload()
    payload["caveats"] = [1, 2, 3]
    with pytest.raises(OutputerValidationError):
        validate_outputer_payload(payload, expected_report_id="eval_test_001")


# ----------------------------------------------------------------------
# get_client env behaviour
# ----------------------------------------------------------------------

def test_get_client_default_is_fake():
    c = get_client(env={})
    assert isinstance(c, DeterministicFakeClient)


def test_get_client_explicit_fake():
    c = get_client(env={"EBF_LLM_PROVIDER": "fake"})
    assert isinstance(c, DeterministicFakeClient)


def test_get_client_unknown_provider_raises_disabled():
    with pytest.raises(DisabledLLMClientError):
        get_client(env={"EBF_LLM_PROVIDER": "anthropic"})


def test_get_client_case_insensitive():
    with pytest.raises(DisabledLLMClientError):
        get_client(env={"EBF_LLM_PROVIDER": "OpenAI"})
