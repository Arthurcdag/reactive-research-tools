"""Anthropic LLM client adapter tests.

All provider tests use injected HTTP clients; no test performs a real
network call or requires a provider key.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.effective_boolean_filter.llm_cache import LLMResponseCache
from src.effective_boolean_filter.llm_client import (
    AnthropicClient,
    DeterministicFakeClient,
    DisabledLLMClientError,
    LLMProviderUnavailable,
    LLMRequest,
    LLMTimeoutError,
    get_client,
    provider_status,
)
from src.effective_boolean_filter.llm_outputer import generate_outputer


SELECTED_REPORT = {
    "id": "eval_provider",
    "effective_polarity": "effective_yes",
    "recommendation": "accept",
    "effectiveness_score": 0.9,
    "issues": [],
}
RECIPE = {
    "selected_candidate": {
        "candidate_id": "clean",
        "claim": "P",
        "argument": "It is not the case that not P. Therefore P.",
    },
    "rank_reason": "clean: accept with 0.900 effectiveness and no error issues",
}


class _Response:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
        json_error: ValueError | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _HTTP:
    def __init__(
        self,
        response: _Response | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response or _Response(payload=_message("ok"))
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> _Response:
        self.calls.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return self.response


def _message(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "ignored-return-model",
        "content": [{"type": "text", "text": text}],
    }


def _good_outputer_payload(summary: str = "selected") -> dict[str, Any]:
    return {
        "summary": summary,
        "why_selected": "The deterministic report selected the clean candidate.",
        "replication_steps": ["Run the wrapper.", "Check the selected candidate."],
        "caveats": ["Provider prose is advisory only."],
        "source_report_id": SELECTED_REPORT["id"],
    }


def test_get_client_default_and_fake_stay_deterministic():
    assert isinstance(get_client(env={}), DeterministicFakeClient)
    assert isinstance(get_client(env={"EBF_LLM_PROVIDER": "fake"}), DeterministicFakeClient)


def test_get_client_valid_anthropic_config():
    client = get_client(
        env={
            "EBF_LLM_PROVIDER": "AnThRoPiC",
            "ANTHROPIC_API_KEY": "sk-test",
            "EBF_LLM_MODEL": "claude-test",
            "EBF_ANTHROPIC_VERSION": "2023-06-01",
            "EBF_LLM_BASE_URL": "https://example.test",
            "EBF_LLM_MAX_TOKENS": "123",
        }
    )
    assert isinstance(client, AnthropicClient)
    assert client.provider == "anthropic"
    assert client.model == "claude-test"


@pytest.mark.parametrize(
    "env, message",
    [
        (
            {"EBF_LLM_PROVIDER": "anthropic", "EBF_LLM_MODEL": "claude-test"},
            "ANTHROPIC_API_KEY",
        ),
        (
            {"EBF_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-test"},
            "EBF_LLM_MODEL",
        ),
        (
            {
                "EBF_LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "sk-test",
                "EBF_LLM_MODEL": "claude-test",
                "EBF_LLM_MAX_TOKENS": "0",
            },
            "EBF_LLM_MAX_TOKENS",
        ),
        (
            {
                "EBF_LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "sk-test",
                "EBF_LLM_MODEL": "claude-test",
                "EBF_LLM_BASE_URL": "example.test",
            },
            "EBF_LLM_BASE_URL",
        ),
    ],
)
def test_get_client_rejects_malformed_anthropic_config(env, message):
    with pytest.raises(DisabledLLMClientError, match=message):
        get_client(env=env)


def test_get_client_unsupported_provider_still_fails_visibly():
    with pytest.raises(DisabledLLMClientError, match="not supported"):
        get_client(env={"EBF_LLM_PROVIDER": "openai"})


def test_provider_status_default_fake():
    assert provider_status(env={}) == {
        "provider": "fake-deterministic",
        "configured": True,
        "live": False,
        "model": "fake-deterministic-1",
        "errors": [],
    }


def test_provider_status_valid_anthropic_config_hides_key_value():
    status = provider_status(
        env={
            "EBF_LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-secret",
            "EBF_LLM_MODEL": "claude-test",
            "EBF_LLM_BASE_URL": "https://example.test/",
            "EBF_LLM_MAX_TOKENS": "123",
        }
    )
    assert status == {
        "provider": "anthropic",
        "configured": True,
        "live": True,
        "model": "claude-test",
        "anthropic_version": "2023-06-01",
        "base_url": "https://example.test",
        "max_tokens": 123,
        "credential_present": True,
        "errors": [],
    }
    assert "sk-secret" not in json.dumps(status)


def test_provider_status_reports_anthropic_config_errors_without_raising():
    status = provider_status(
        env={
            "EBF_LLM_PROVIDER": "anthropic",
            "EBF_LLM_BASE_URL": "example.test",
            "EBF_LLM_MAX_TOKENS": "nope",
        }
    )
    assert status["provider"] == "anthropic"
    assert status["configured"] is False
    assert status["credential_present"] is False
    assert "ANTHROPIC_API_KEY is required" in status["errors"]
    assert "EBF_LLM_MODEL is required" in status["errors"]
    assert any("EBF_LLM_BASE_URL" in error for error in status["errors"])
    assert any("EBF_LLM_MAX_TOKENS" in error for error in status["errors"])


def test_provider_status_reports_unsupported_provider():
    status = provider_status(env={"EBF_LLM_PROVIDER": "openai"})
    assert status == {
        "provider": "openai",
        "configured": False,
        "live": False,
        "model": None,
        "errors": ["Unsupported provider. Use unset/fake or anthropic."],
    }


def test_anthropic_client_posts_messages_shape():
    http = _HTTP(_Response(payload=_message("part one\npart two")))
    client = AnthropicClient(
        api_key="sk-test",
        model="claude-test",
        anthropic_version="2023-06-01",
        base_url="https://example.test/",
        max_tokens=321,
        http_client=http,
    )
    response = client.generate(
        LLMRequest(
            system="system text",
            user='{"data": true}',
            prompt_version="test_v1",
            style="brief",
            timeout_seconds=7.5,
        )
    )
    assert response.raw_text == "part one\npart two"
    assert response.provider == "anthropic"
    assert response.model == "claude-test"
    call = http.calls[0]
    assert call["url"] == "https://example.test/v1/messages"
    assert call["headers"] == {
        "x-api-key": "sk-test",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    assert call["json"] == {
        "model": "claude-test",
        "max_tokens": 321,
        "temperature": 0,
        "system": "system text",
        "messages": [{"role": "user", "content": '{"data": true}'}],
    }
    assert call["timeout"] == 7.5


def test_anthropic_client_joins_multiple_text_blocks():
    http = _HTTP(
        _Response(
            payload={
                "content": [
                    {"type": "text", "text": "alpha"},
                    {"type": "tool_use", "name": "ignored"},
                    {"type": "text", "text": "beta"},
                ]
            }
        )
    )
    client = AnthropicClient(
        api_key="sk-test",
        model="claude-test",
        http_client=http,
    )
    response = client.generate(
        LLMRequest(system="s", user="u", prompt_version="v", style="brief")
    )
    assert response.raw_text == "alphabeta"


def test_anthropic_client_maps_http_error_to_provider_unavailable():
    http = _HTTP(
        _Response(
            status_code=429,
            headers={"request-id": "req_test"},
            payload={
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "too many requests",
                },
            },
        )
    )
    client = AnthropicClient(api_key="sk-test", model="claude-test", http_client=http)
    with pytest.raises(LLMProviderUnavailable, match="rate_limit_error"):
        client.generate(LLMRequest(system="s", user="u", prompt_version="v", style="brief"))


def test_anthropic_client_maps_timeout():
    http = _HTTP(error=httpx.TimeoutException("timed out"))
    client = AnthropicClient(api_key="sk-test", model="claude-test", http_client=http)
    with pytest.raises(LLMTimeoutError):
        client.generate(LLMRequest(system="s", user="u", prompt_version="v", style="brief"))


@pytest.mark.parametrize(
    "response",
    [
        _Response(payload={"content": []}),
        _Response(payload={"content": [{"type": "json", "text": "{}"}]}),
        _Response(json_error=ValueError("not json")),
    ],
)
def test_anthropic_client_rejects_invalid_response_shape(response):
    http = _HTTP(response)
    client = AnthropicClient(api_key="sk-test", model="claude-test", http_client=http)
    with pytest.raises(LLMProviderUnavailable):
        client.generate(LLMRequest(system="s", user="u", prompt_version="v", style="brief"))


def test_outputer_cache_isolates_fake_and_anthropic_provider_keys():
    cache = LLMResponseCache()
    fake = DeterministicFakeClient(
        scripted={"brief": json.dumps(_good_outputer_payload("fake"))}
    )
    anthropic_http = _HTTP(
        _Response(payload=_message(json.dumps(_good_outputer_payload("anthropic"))))
    )
    anthropic = AnthropicClient(
        api_key="sk-test",
        model="claude-test",
        http_client=anthropic_http,
    )

    fake_result = generate_outputer(
        selected_report=SELECTED_REPORT,
        replication_recipe=RECIPE,
        style="brief",
        client=fake,
        cache=cache,
    )
    anthropic_result = generate_outputer(
        selected_report=SELECTED_REPORT,
        replication_recipe=RECIPE,
        style="brief",
        client=anthropic,
        cache=cache,
    )
    second_anthropic = generate_outputer(
        selected_report=SELECTED_REPORT,
        replication_recipe=RECIPE,
        style="brief",
        client=anthropic,
        cache=cache,
    )

    assert fake_result.cache_key != anthropic_result.cache_key
    assert fake_result.validated_output["summary"] == "fake"
    assert anthropic_result.validated_output["summary"] == "anthropic"
    assert anthropic_result.cached is False
    assert second_anthropic.cached is True
    assert len(anthropic_http.calls) == 1
