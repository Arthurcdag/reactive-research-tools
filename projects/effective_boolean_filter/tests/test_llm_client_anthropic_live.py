"""Opt-in live Anthropic provider smoke tests.

Every other provider test in this suite uses injected fakes and never
touches the network. That is correct for CI, but it means a breaking
change in the real Messages API request/response shape would land
unnoticed. These tests close that gap with the cheapest credible check:
a couple of real round-trips behind an opt-in marker.

Run them explicitly:

    ANTHROPIC_API_KEY=sk-... EBF_LLM_MODEL=claude-... pytest -m live

They are excluded from the default run (`addopts = -m 'not live'` in
``pyproject.toml``) and additionally skip when ``ANTHROPIC_API_KEY`` is
absent, so a bare `pytest -m live` with no key is a clean skip rather
than a failure.

Cost note: each test makes one short, low-token, ``temperature: 0``
request. Keep it that way — this file is a smoke test, not a behavioural
suite.
"""
from __future__ import annotations

import os

import pytest

from src.effective_boolean_filter.llm_client import (
    AnthropicClient,
    LLMRequest,
    LLMResponse,
    get_client,
)
from src.effective_boolean_filter.llm_cache import LLMResponseCache
from src.effective_boolean_filter.llm_outputer import (
    OutputerResult,
    generate_outputer,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set; live provider smoke tests skipped",
    ),
]


def _live_env() -> dict[str, str]:
    """Resolve a live-provider env from the process environment.

    ``EBF_LLM_MODEL`` is required for the Anthropic adapter; default it to
    a current small model so a bare `ANTHROPIC_API_KEY=...` invocation
    still works.
    """
    env = {
        "EBF_LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
        "EBF_LLM_MODEL": os.environ.get("EBF_LLM_MODEL", "claude-haiku-4-5-20251001"),
    }
    for optional in ("EBF_ANTHROPIC_VERSION", "EBF_LLM_BASE_URL", "EBF_LLM_MAX_TOKENS"):
        if optional in os.environ:
            env[optional] = os.environ[optional]
    return env


def test_anthropic_live_messages_api_round_trip():
    """Transport + response-shape check: a real request returns an
    :class:`LLMResponse` with non-empty text. This is what catches a
    breaking change in the Messages API request or response shape."""
    client = get_client(env=_live_env())
    assert isinstance(client, AnthropicClient)

    response = client.generate(
        LLMRequest(
            system=(
                "You are a test harness probe. Reply with exactly the single "
                "word OK and nothing else."
            ),
            user="ping",
            prompt_version="live_smoke_v1",
            style="brief",
            timeout_seconds=30.0,
        )
    )

    assert isinstance(response, LLMResponse)
    assert response.provider == "anthropic"
    assert response.model == _live_env()["EBF_LLM_MODEL"]
    assert response.raw_text.strip(), "live provider returned empty text"


def test_anthropic_live_outputer_end_to_end():
    """Full outputer path against a real provider: generate → parse →
    strict schema validation. This catches model output that no longer
    satisfies the outputer JSON contract."""
    selected_report = {
        "id": "eval_live_smoke",
        "effective_polarity": "effective_yes",
        "recommendation": "accept",
        "effectiveness_score": 0.9,
        "issues": [],
    }
    replication_recipe = {
        "selected_candidate": {
            "candidate_id": "clean",
            "claim": "P",
            "argument": "It is not the case that not P. Therefore P.",
        },
        "rank_reason": "clean: accept with 0.900 effectiveness and no error issues",
    }

    result = generate_outputer(
        selected_report=selected_report,
        replication_recipe=replication_recipe,
        style="brief",
        client=get_client(env=_live_env()),
        # fresh cache so the assertion below sees a real provider call
        cache=LLMResponseCache(),
    )

    assert isinstance(result, OutputerResult)
    assert result.provider == "anthropic"
    assert result.cached is False
    validated = result.validated_output
    # validate_outputer_payload already enforced the schema; re-assert the
    # load-bearing invariant so a failure here reads clearly.
    assert validated["source_report_id"] == "eval_live_smoke"
    assert validated["summary"].strip()
    assert validated["why_selected"].strip()
    assert validated["replication_steps"]
