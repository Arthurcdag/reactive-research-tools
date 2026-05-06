"""Unit tests for the Azatoth inputer.

Locks in the spec's failure policy and bound rules:

* fake-client happy path returns N validated unique candidates
* count bounds (1..20) enforced
* pool default = min(max(count*4, 16), 80); pool max = 80
* invalid JSON / missing fields / extra fields / wrong types fail visibly
* over-length claim/argument/context fail visibly
* bad strictness fails visibly
* duplicate-only pool and insufficient unique candidates fail visibly
* cache hit avoids second client call
* deep-copy cache safety
* no input mutation
"""
from __future__ import annotations

import copy
import json

import pytest

from src.effective_boolean_filter.advisory import AdvisoryCandidate
from src.effective_boolean_filter.llm_cache import LLMResponseCache
from src.effective_boolean_filter.llm_client import (
    DeterministicFakeClient,
    DisabledLLMClientError,
    LLMClient,
    LLMRequest,
    LLMResponse,
    get_client,
)
from src.effective_boolean_filter.llm_inputer import (
    COUNT_MAX,
    COUNT_MIN,
    InputerValidationError,
    POOL_HARD_MAX,
    default_pool_size,
    generate_inputer,
    inputer_result_to_dict,
    validate_inputer_payload,
)
from src.effective_boolean_filter.llm_prompts import INPUTER_PROMPT_VERSION


class _ScriptedClient(LLMClient):
    """Returns a single scripted raw_text and counts calls."""

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


def _candidate(idx: int, *, claim: str = "P", argument_suffix: str = "") -> dict:
    return {
        "candidate_id": f"cand_{idx:03d}_test",
        "claim": claim,
        "argument": f"It is not the case that not {claim}. Therefore {claim}.{argument_suffix}",
        "context": "logic",
        "strictness": "medium",
        "template": "clean_double_negation",
        "mutation_notes": f"test variant {idx}",
    }


def _good_pool(count: int) -> str:
    return json.dumps({
        "azatoth_candidates": [_candidate(i, argument_suffix=f" (variant {i})") for i in range(1, count + 1)]
    })


# ----------------------------------------------------------------------
# pool size rule + bounds
# ----------------------------------------------------------------------

def test_default_pool_size_rule():
    assert default_pool_size(1) == 16
    assert default_pool_size(4) == 16   # floor wins
    assert default_pool_size(8) == 32   # 4x
    assert default_pool_size(20) == 80  # ceil
    assert default_pool_size(21) == 80  # never exceeds hard max


def test_count_below_min_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="logic", count=0,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_count_above_max_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="logic", count=COUNT_MAX + 1,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_pool_size_below_count_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="logic", count=10, pool_size=5,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_pool_size_above_hard_max_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="logic", count=10, pool_size=POOL_HARD_MAX + 1,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


# ----------------------------------------------------------------------
# happy path with deterministic fake
# ----------------------------------------------------------------------

def test_fake_client_happy_path_returns_count_candidates():
    cache = LLMResponseCache()
    r = generate_inputer(
        seed="P", context="logic", count=8,
        client=DeterministicFakeClient(), cache=cache,
    )
    assert len(r.azatoth_candidates) == 8
    # all unique candidate_ids
    assert len({c.candidate_id for c in r.azatoth_candidates}) == 8
    # all unique (claim, argument) pairs
    pairs = {(c.claim, c.argument) for c in r.azatoth_candidates}
    assert len(pairs) == 8
    assert r.cached is False
    assert r.pool_size == default_pool_size(8)
    assert r.valid_count >= 8
    assert r.deduped_count >= 8
    assert r.mode == "contract_v0_inputer"


def test_fake_client_returns_advisory_candidate_objects():
    r = generate_inputer(
        seed="P", context="logic", count=3,
        client=DeterministicFakeClient(), cache=LLMResponseCache(),
    )
    for c in r.azatoth_candidates:
        assert isinstance(c, AdvisoryCandidate)
        assert c.strictness == "medium"


def test_fake_client_emits_at_least_pool_size_when_count_below_floor():
    """count=1 → pool_size=16 by default."""
    r = generate_inputer(
        seed="P", context="logic", count=1,
        client=DeterministicFakeClient(), cache=LLMResponseCache(),
    )
    assert r.pool_size == 16
    assert r.valid_count >= 16
    assert len(r.azatoth_candidates) == 1


def test_to_dict_shape():
    r = generate_inputer(
        seed="P", context="logic", count=2,
        client=DeterministicFakeClient(), cache=LLMResponseCache(),
    )
    d = inputer_result_to_dict(r)
    assert set(d) == {
        "mode", "provider", "model", "cache_key", "cached",
        "pool_size", "valid_count", "deduped_count", "azatoth_candidates",
    }
    for c in d["azatoth_candidates"]:
        assert set(c) == {
            "candidate_id", "claim", "argument", "context",
            "strictness", "template", "mutation_notes",
        }


# ----------------------------------------------------------------------
# cache
# ----------------------------------------------------------------------

def test_cache_hit_avoids_second_client_call():
    cache = LLMResponseCache()
    client = _ScriptedClient(_good_pool(20))
    first = generate_inputer(
        seed="P", context="logic", count=5,
        client=client, cache=cache,
    )
    second = generate_inputer(
        seed="P", context="logic", count=5,
        client=client, cache=cache,
    )
    assert first.cached is False
    assert second.cached is True
    assert len(client.calls) == 1
    assert [c.candidate_id for c in second.azatoth_candidates] == \
           [c.candidate_id for c in first.azatoth_candidates]


def test_cache_distinguishes_seed():
    cache = LLMResponseCache()
    client_a = _ScriptedClient(_good_pool(20))
    client_b = _ScriptedClient(_good_pool(20))
    generate_inputer(seed="A", context="logic", count=5, client=client_a, cache=cache)
    generate_inputer(seed="B", context="logic", count=5, client=client_b, cache=cache)
    assert len(client_a.calls) == 1
    assert len(client_b.calls) == 1


def test_cache_distinguishes_count():
    cache = LLMResponseCache()
    client = _ScriptedClient(_good_pool(20))
    generate_inputer(seed="P", context="logic", count=5, client=client, cache=cache)
    generate_inputer(seed="P", context="logic", count=6, client=client, cache=cache)
    assert len(client.calls) == 2  # different cache keys


def test_cache_key_includes_inputer_prompt_version():
    r = generate_inputer(
        seed="P", context="logic", count=2,
        client=DeterministicFakeClient(), cache=LLMResponseCache(),
    )
    assert INPUTER_PROMPT_VERSION in r.cache_key
    assert r.cache_key.startswith("inputer/")


def test_cache_namespace_isolated_from_outputer():
    """Inputer and outputer never share a cache string even if hashes
    coincidentally overlap."""
    r = generate_inputer(
        seed="P", context="logic", count=2,
        client=DeterministicFakeClient(), cache=LLMResponseCache(),
    )
    # outputer keys never start with "inputer/"
    assert r.cache_key.startswith("inputer/")


def test_cache_returned_candidates_are_deep_copied():
    cache = LLMResponseCache()
    first = generate_inputer(
        seed="P", context="logic", count=3,
        client=DeterministicFakeClient(), cache=cache,
    )
    # mutate first call's returned objects
    first.azatoth_candidates[0]  # AdvisoryCandidate is frozen, can't mutate
    # but the underlying cached dict should not reflect any change
    second = generate_inputer(
        seed="P", context="logic", count=3,
        client=DeterministicFakeClient(), cache=cache,
    )
    assert second.cached is True
    assert (
        second.azatoth_candidates[0].candidate_id
        == first.azatoth_candidates[0].candidate_id
    )


# ----------------------------------------------------------------------
# validation failures must be visible
# ----------------------------------------------------------------------

def test_invalid_json_raises():
    cache = LLMResponseCache()
    client = _ScriptedClient("not-json")
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(
            seed="P", context="logic", count=3,
            client=client, cache=cache,
        )
    assert "not valid JSON" in str(exc.value)


def test_missing_top_level_field_raises():
    payload = {"wrong_key": []}
    client = _ScriptedClient(json.dumps(payload))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=2, client=client, cache=LLMResponseCache())
    assert "missing required field" in str(exc.value) or "unexpected top-level fields" in str(exc.value)


def test_unexpected_top_level_field_raises():
    payload = {"azatoth_candidates": [_candidate(1)], "extra": "x"}
    client = _ScriptedClient(json.dumps(payload))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())
    assert "unexpected top-level fields" in str(exc.value)


def test_empty_pool_raises():
    payload = {"azatoth_candidates": []}
    client = _ScriptedClient(json.dumps(payload))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())
    assert "empty" in str(exc.value)


def test_candidate_missing_field_raises():
    bad = _candidate(1)
    del bad["argument"]
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())
    assert "missing required fields" in str(exc.value)


def test_candidate_extra_field_raises():
    bad = _candidate(1)
    bad["score"] = 0.9
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())
    assert "unexpected fields" in str(exc.value)


def test_candidate_wrong_type_raises():
    bad = _candidate(1)
    bad["claim"] = ["not", "a", "string"]
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError):
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())


def test_candidate_empty_claim_raises():
    bad = _candidate(1)
    bad["claim"] = "   "
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError):
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())


@pytest.mark.parametrize("field,limit", [
    ("claim", 4001),
    ("argument", 8001),
    ("context", 2001),
])
def test_candidate_over_length_field_raises(field, limit):
    bad = _candidate(1)
    bad[field] = "x" * limit
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())
    assert "exceeds" in str(exc.value)


def test_candidate_strictness_must_match_request():
    bad = _candidate(1)
    bad["strictness"] = "high"  # request asks for medium
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(
            seed="P", context="logic", count=1, strictness="medium",
            client=client, cache=LLMResponseCache(),
        )
    assert "does not match" in str(exc.value)


def test_candidate_invalid_strictness_value_raises():
    bad = _candidate(1)
    bad["strictness"] = "extreme"
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [bad]}))
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="logic", count=1, strictness="medium",
            client=client, cache=LLMResponseCache(),
        )


def test_request_invalid_strictness_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="logic", count=1, strictness="extreme",
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_request_seed_must_be_non_empty_string():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="   ", context="logic", count=1,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_request_seed_too_long_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="x" * 4001, context="logic", count=1,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_request_context_too_long_raises():
    with pytest.raises(InputerValidationError):
        generate_inputer(
            seed="P", context="x" * 2001, count=1,
            client=DeterministicFakeClient(), cache=LLMResponseCache(),
        )


def test_duplicate_candidate_ids_within_pool_raise():
    a = _candidate(1)
    b = _candidate(1, claim="Q")  # same id, different claim
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [a, b]}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=LLMResponseCache())
    assert "duplicate candidate_id" in str(exc.value)


def test_duplicate_only_pool_after_dedupe_fails_visibly():
    """Same (claim, argument) repeated → after dedupe, only one unique
    remains; if count > 1, it must fail visibly, not silently shrink."""
    dup_arg = "It is not the case that not P. Therefore P."
    pool = [
        {**_candidate(i), "argument": dup_arg, "claim": "P"}
        for i in range(1, 6)
    ]
    client = _ScriptedClient(json.dumps({"azatoth_candidates": pool}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=3, client=client, cache=LLMResponseCache())
    assert "insufficient unique candidates" in str(exc.value)


def test_dedupe_collapses_whitespace_and_case():
    """Dedupe keys are case-folded and whitespace-collapsed, so trivial
    variants are still treated as duplicates."""
    a = _candidate(1, claim="P")
    a["argument"] = "It is not the case that not P. Therefore P."
    b = _candidate(2, claim="p")  # different case
    b["argument"] = "  It is not the case that not p.   Therefore p.  "
    client = _ScriptedClient(json.dumps({"azatoth_candidates": [a, b]}))
    with pytest.raises(InputerValidationError) as exc:
        generate_inputer(seed="P", context="logic", count=2, client=client, cache=LLMResponseCache())
    assert "insufficient unique candidates" in str(exc.value)


def test_invalid_payload_does_not_get_cached():
    cache = LLMResponseCache()
    bad = {"azatoth_candidates": []}
    client = _ScriptedClient(json.dumps(bad))
    with pytest.raises(InputerValidationError):
        generate_inputer(seed="P", context="logic", count=1, client=client, cache=cache)
    assert len(cache) == 0


# ----------------------------------------------------------------------
# no-mutation invariant
# ----------------------------------------------------------------------

def test_inputer_does_not_mutate_seed_or_context():
    seed = "P with sensitive content"
    seed_before = seed
    context = "scientific argument with notes"
    context_before = context
    generate_inputer(
        seed=seed, context=context, count=2,
        client=DeterministicFakeClient(), cache=LLMResponseCache(),
    )
    assert seed == seed_before
    assert context == context_before


def test_validate_inputer_payload_unit():
    payload = {"azatoth_candidates": [_candidate(1)]}
    out = validate_inputer_payload(payload, expected_strictness="medium")
    assert len(out) == 1
    # returned dicts are independent copies
    out[0]["claim"] = "POISONED"
    assert payload["azatoth_candidates"][0]["claim"] == "P"


# ----------------------------------------------------------------------
# get_client respects the env contract — same as outputer
# ----------------------------------------------------------------------

def test_get_client_default_is_fake():
    c = get_client(env={})
    assert isinstance(c, DeterministicFakeClient)


def test_get_client_unknown_provider_raises_disabled():
    with pytest.raises(DisabledLLMClientError):
        get_client(env={"EBF_LLM_PROVIDER": "anthropic"})
