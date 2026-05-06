"""API coverage for the Anthropic provider adapter path."""
from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


class _Response:
    def __init__(self, payload: Any) -> None:
        self.status_code = 200
        self._payload = payload
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        return self._payload


class _HTTP:
    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
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
        text = self._texts.pop(0)
        return _Response({"content": [{"type": "text", "text": text}]})


def _anthropic_client(*texts: str):
    from src.effective_boolean_filter.llm_client import AnthropicClient

    http = _HTTP(list(texts))
    client = AnthropicClient(
        api_key="sk-test",
        model="claude-test",
        base_url="https://example.test",
        http_client=http,
    )
    return client, http


def _test_client(llm_client):
    from fastapi.testclient import TestClient

    from src.effective_boolean_filter.api import create_app
    from src.effective_boolean_filter.llm_cache import LLMResponseCache

    return TestClient(
        create_app(
            llm_client=llm_client,
            outputer_cache=LLMResponseCache(),
        )
    )


def test_api_azatoth_input_uses_injected_anthropic_client():
    raw = json.dumps(
        {
            "azatoth_candidates": [
                {
                    "candidate_id": "anthropic_clean",
                    "claim": "P",
                    "argument": "It is not the case that not P. Therefore P.",
                    "context": "logic",
                    "strictness": "medium",
                    "template": "clean_double_negation",
                    "mutation_notes": "provider candidate",
                }
            ]
        }
    )
    client, http = _anthropic_client(raw)
    response = _test_client(client).post(
        "/advisory/azatoth/input",
        json={
            "seed": "P",
            "context": "logic",
            "count": 1,
            "strictness": "medium",
            "pool_size": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-test"
    assert body["azatoth_candidates"][0]["candidate_id"] == "anthropic_clean"
    assert http.calls[0]["json"]["messages"][0]["role"] == "user"


def test_api_nyahlothep_output_uses_injected_anthropic_client():
    from src.effective_boolean_filter.advisory import (
        advisory_run_to_dict,
        run_advisory_wrapper,
    )

    run = advisory_run_to_dict(run_advisory_wrapper("P", count=1))
    selected_report = run["selected_report"]
    raw = json.dumps(
        {
            "summary": "Anthropic narration.",
            "why_selected": "The deterministic filter selected the clean candidate.",
            "replication_steps": ["Run the wrapper.", "Check the selected id."],
            "caveats": ["Provider prose is advisory only."],
            "source_report_id": selected_report["id"],
        }
    )
    client, http = _anthropic_client(raw)
    response = _test_client(client).post(
        "/advisory/nyahlothep/output",
        json={
            "selected_report": selected_report,
            "replication_recipe": run["replication_recipe"],
            "style": "brief",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-test"
    assert body["validated_output"]["summary"] == "Anthropic narration."
    assert http.calls[0]["json"]["temperature"] == 0


def test_api_anthropic_invalid_json_still_returns_422():
    client, _http = _anthropic_client("not json")
    response = _test_client(client).post(
        "/advisory/azatoth/input",
        json={
            "seed": "P",
            "context": "logic",
            "count": 1,
            "strictness": "medium",
            "pool_size": 1,
        },
    )
    assert response.status_code == 422
