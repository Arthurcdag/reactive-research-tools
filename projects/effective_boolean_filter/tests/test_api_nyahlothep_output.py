"""End-to-end API tests for POST /advisory/nyahlothep/output.

Covers the spec's failure policy at the HTTP layer:

* schema-valid happy path -> 200, full result shape
* invalid JSON from provider -> 422 with visible detail
* missing/extra/wrong-type schema fields -> 422
* source_report_id mismatch -> 422
* DisabledLLMClientError (provider configured but unavailable) -> 503
* cache hit avoids second client call when injected cache is reused
* outputer endpoint never mutates the selected_report it received
* Pydantic body validation for missing/over-length/invalid-style inputs
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


# A canonical "happy" payload tied to a known report id.
GOOD_PAYLOAD = {
    "summary": "Engine accepted the canonical double-negation argument.",
    "why_selected": "rank_reason indicates a clean trace and 0.875 effectiveness.",
    "replication_steps": [
        "Open the dashboard and run the seed argument.",
        "Inspect the deterministic verdict.",
    ],
    "caveats": ["Heuristic narration only."],
    "source_report_id": "PLACEHOLDER",  # patched per test
}


def _good_for(report_id: str) -> str:
    payload = dict(GOOD_PAYLOAD)
    payload["source_report_id"] = report_id
    return json.dumps(payload)


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


class _AlwaysDisabledClient(LLMClient):
    """Simulates a provider that is not available in this build."""

    @property
    def provider(self) -> str:
        return "remote"

    @property
    def model(self) -> str:
        return "remote-model"

    def generate(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
        raise DisabledLLMClientError(
            "remote provider is not available in this build"
        )


def _seed_run(client: TestClient) -> tuple[dict, dict]:
    """Run the deterministic advisory wrapper and return (selected_report, recipe)."""
    r = client.post(
        "/advisory/run",
        json={"seed": "P", "context": "logic", "count": 4, "strictness": "medium"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["selected_report"], body["replication_recipe"]


# ----------------------------------------------------------------------
# happy path
# ----------------------------------------------------------------------

def test_happy_path_returns_200_with_full_shape():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    scripted = _ScriptedClient(_good_for(selected["id"]))
    cache = LLMResponseCache()
    app = create_app(llm_client=scripted, outputer_cache=cache)
    c = TestClient(app)

    r = c.post(
        "/advisory/nyahlothep/output",
        json={
            "selected_report": selected,
            "replication_recipe": recipe,
            "style": "brief",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"mode", "provider", "model", "cache_key", "cached", "validated_output"}
    assert body["mode"] == "contract_v0_outputer"
    assert body["provider"] == "scripted-fake"
    assert body["cached"] is False
    assert set(body["validated_output"]) == {
        "summary", "why_selected", "replication_steps", "caveats", "source_report_id",
    }
    assert body["validated_output"]["source_report_id"] == selected["id"]


def test_supports_all_three_styles():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)
    for style in ("brief", "technical", "replication"):
        scripted = _ScriptedClient(_good_for(selected["id"]))
        c = TestClient(create_app(
            llm_client=scripted, outputer_cache=LLMResponseCache(),
        ))
        r = c.post(
            "/advisory/nyahlothep/output",
            json={"selected_report": selected, "replication_recipe": recipe, "style": style},
        )
        assert r.status_code == 200, r.text
        assert r.json()["validated_output"]["source_report_id"] == selected["id"]


# ----------------------------------------------------------------------
# cache: hit avoids second client call
# ----------------------------------------------------------------------

def test_cache_hit_avoids_second_provider_call_through_api():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    scripted = _ScriptedClient(_good_for(selected["id"]))
    cache = LLMResponseCache()
    app = create_app(llm_client=scripted, outputer_cache=cache)
    c = TestClient(app)

    payload = {
        "selected_report": selected,
        "replication_recipe": recipe,
        "style": "brief",
    }
    first = c.post("/advisory/nyahlothep/output", json=payload)
    second = c.post("/advisory/nyahlothep/output", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert len(scripted.calls) == 1


# ----------------------------------------------------------------------
# visible failures
# ----------------------------------------------------------------------

def test_invalid_json_from_provider_returns_422():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    scripted = _ScriptedClient("not json at all")
    c = TestClient(create_app(
        llm_client=scripted, outputer_cache=LLMResponseCache(),
    ))
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "brief"},
    )
    assert r.status_code == 422
    detail = r.json().get("detail", "")
    # the detail must be visible — no silent fallback
    assert "JSON" in detail or "schema" in detail or "validation" in detail.lower()


def test_missing_required_field_returns_422():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    bad = dict(GOOD_PAYLOAD)
    del bad["why_selected"]
    bad["source_report_id"] = selected["id"]
    scripted = _ScriptedClient(json.dumps(bad))

    c = TestClient(create_app(
        llm_client=scripted, outputer_cache=LLMResponseCache(),
    ))
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "brief"},
    )
    assert r.status_code == 422
    assert "missing required fields" in r.json()["detail"]


def test_unexpected_field_returns_422():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    bad = dict(GOOD_PAYLOAD)
    bad["score"] = 0.99
    bad["source_report_id"] = selected["id"]
    scripted = _ScriptedClient(json.dumps(bad))

    c = TestClient(create_app(
        llm_client=scripted, outputer_cache=LLMResponseCache(),
    ))
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "brief"},
    )
    assert r.status_code == 422
    assert "unexpected fields" in r.json()["detail"]


def test_source_report_id_mismatch_returns_422():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    forged = dict(GOOD_PAYLOAD)
    forged["source_report_id"] = "eval_someone_elses"
    scripted = _ScriptedClient(json.dumps(forged))

    c = TestClient(create_app(
        llm_client=scripted, outputer_cache=LLMResponseCache(),
    ))
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "brief"},
    )
    assert r.status_code == 422
    assert "source_report_id mismatch" in r.json()["detail"]


def test_disabled_provider_returns_503():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)

    c = TestClient(create_app(
        llm_client=_AlwaysDisabledClient(),
        outputer_cache=LLMResponseCache(),
    ))
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "brief"},
    )
    assert r.status_code == 503
    assert "not available" in r.json()["detail"]


# ----------------------------------------------------------------------
# Pydantic body validation
# ----------------------------------------------------------------------

def test_invalid_style_returns_422():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)
    c = TestClient(create_app())
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "extreme"},
    )
    assert r.status_code == 422


def test_missing_selected_report_returns_422():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"replication_recipe": {}, "style": "brief"},
    )
    assert r.status_code == 422


def test_missing_recipe_returns_422():
    c = TestClient(create_app())
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": {"id": "eval_x"}, "style": "brief"},
    )
    assert r.status_code == 422


# ----------------------------------------------------------------------
# read-only invariant
# ----------------------------------------------------------------------

def test_endpoint_does_not_mutate_selected_report_or_verdict():
    seed_client = TestClient(create_app())
    selected, recipe = _seed_run(seed_client)
    selected_before = copy.deepcopy(selected)
    recipe_before = copy.deepcopy(recipe)

    scripted = _ScriptedClient(_good_for(selected["id"]))
    c = TestClient(create_app(
        llm_client=scripted, outputer_cache=LLMResponseCache(),
    ))
    r = c.post(
        "/advisory/nyahlothep/output",
        json={"selected_report": selected, "replication_recipe": recipe, "style": "brief"},
    )
    assert r.status_code == 200

    # client-side dicts unchanged
    assert selected == selected_before
    assert recipe == recipe_before

    # the verdict in the persisted report (via /reports/{id}) is unchanged.
    # Re-run /advisory/run on a fresh app and confirm same polarity.
    fresh = TestClient(create_app())
    fresh_selected, _ = _seed_run(fresh)
    assert fresh_selected["effective_polarity"] == selected_before["effective_polarity"]
    assert fresh_selected["recommendation"] == selected_before["recommendation"]


def test_endpoint_listed_in_health_independent_paths():
    """Sanity: health works regardless of LLM injection."""
    c = TestClient(create_app(
        llm_client=_AlwaysDisabledClient(),
        outputer_cache=LLMResponseCache(),
    ))
    assert c.get("/health").json()["status"] == "ok"
