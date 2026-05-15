"""API smoke test (spec section 11). Skips cleanly when FastAPI is not installed."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


def _client():
    from fastapi.testclient import TestClient
    from src.effective_boolean_filter.api import create_app
    return TestClient(create_app())


def test_evaluate_endpoint_returns_full_shape():
    client = _client()
    r = client.post(
        "/evaluate_argument",
        json={
            "claim": "X is true",
            "argument": "There is no evidence against X, therefore X is true",
            "context": "science",
            "strictness": "medium",
        },
    )
    assert r.status_code == 200
    body = r.json()
    for key in (
        "id", "effective_polarity", "effectiveness_score", "bogusness_score",
        "score_vector", "trace", "issues", "probes", "contradiction",
        "recommendation",
    ):
        assert key in body
    assert body["effective_polarity"] in {"untracked_shift", "unstable"}


def test_dashboard_root_serves_html():
    client = _client()
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "Effective Boolean Filter" in r.text
    assert "/evaluate_argument" in r.text


def test_dashboard_has_all_four_sample_presets():
    body = _client().get("/").text
    for preset in (
        "clean_double_negation",
        "epistemic_shift",
        "scope_shift",
        "contained_contradiction",
    ):
        assert f'data-preset="{preset}"' in body, (
            f"missing preset button {preset!r}"
        )


def test_dashboard_has_score_vector_section():
    body = _client().get("/").text
    assert 'id="score-vector"' in body
    # all eight ScoreVector field labels must be referenced in the JS table
    for key in (
        "negation_consistency",
        "scope_preservation",
        "definition_stability",
        "context_fit",
        "contradiction_containment",
        "reactive_performance",
        "testability",
        "implementation_relevance",
    ):
        assert key in body, f"score-vector field {key!r} missing from dashboard"


def test_dashboard_has_copy_json_button_and_feedback():
    body = _client().get("/").text
    assert 'id="copy-json"' in body
    # explicit/visible confirmation slot per the developer brief
    assert 'id="copy-feedback"' in body
    # the handler must use the user-activation gated Clipboard API
    assert "navigator.clipboard.writeText" in body


def test_dashboard_has_advisory_wrapper_controls():
    body = _client().get("/").text
    for fragment in (
        'id="advisory-panel"',
        'id="advisory-seed"',
        'id="advisory-count"',
        'id="run-wrapper"',
        'id="advisory-ranking"',
        'id="advisory-trace-gates"',
        'id="selected-candidate"',
        'id="load-selected"',
        "/advisory/run",
    ):
        assert fragment in body


def test_dashboard_has_selected_candidate_loading_hooks():
    body = _client().get("/").text
    assert "replication_recipe.selected_candidate" in body
    assert "loadSelectedCandidate" in body
    assert "renderAdvisory" in body
    assert "renderAdvisoryTraceGates" in body


def test_dashboard_no_inline_event_handlers():
    """CSP forbids inline scripts; preset/copy buttons must wire up via
    addEventListener, not onclick=... attributes."""
    body = _client().get("/").text
    # crude but effective: no `onclick=`, `onsubmit=`, etc. anywhere
    for attr in ("onclick=", "onsubmit=", "onload=", "onerror=", "onmouseover="):
        assert attr not in body, f"inline event handler {attr!r} found in dashboard"


def test_dashboard_has_outputer_panel():
    """Nyahlothep outputer V1 panel must exist and reference the new endpoint."""
    body = _client().get("/").text
    for fragment in (
        'id="outputer-section"',
        'id="outputer-style"',
        'id="generate-output"',
        'id="outputer-status"',
        'id="outputer-result"',
        "/advisory/nyahlothep/output",
        # all three styles in the select
        'value="brief"',
        'value="technical"',
        'value="replication"',
    ):
        assert fragment in body, f"missing outputer fragment {fragment!r}"


def test_dashboard_outputer_renders_via_textContent():
    """Outputer JS must build DOM nodes via textContent — never innerHTML
    — for each validated_output field. We grep for the calls."""
    body = _client().get("/").text
    # signature calls present
    assert "renderOutputerOutput" in body
    assert ".textContent" in body
    # no innerHTML escape hatch in the outputer code path
    # (the dashboard nowhere uses innerHTML; this guard catches future regressions)
    assert ".innerHTML" not in body


def test_dashboard_has_azatoth_source_control():
    """Inputer V1 surface: source select with both options + inputer
    status panel + the new endpoint reference."""
    body = _client().get("/").text
    for fragment in (
        'id="advisory-source"',
        'value="deterministic"',
        'value="inputer"',
        'id="inputer-status-section"',
        'id="inputer-provider"',
        'id="inputer-model"',
        'id="inputer-cached"',
        'id="inputer-pool"',
        'id="inputer-valid"',
        'id="inputer-deduped"',
        'id="inputer-returned"',
    ):
        assert fragment in body, f"missing inputer fragment {fragment!r}"


def test_dashboard_has_advisory_ledger_replay_controls():
    body = _client().get("/").text
    for fragment in (
        'id="ledger-section"',
        'id="ledger-entry"',
        'id="ledger-sequence"',
        'id="ledger-hash"',
        'id="replay-ledger"',
        'id="ledger-replay-status"',
        "/advisory/ledger/",
        "replayLedgerEntry",
        "renderLedgerStatus",
    ):
        assert fragment in body, f"missing ledger fragment {fragment!r}"


def test_dashboard_has_provider_status_controls():
    body = _client().get("/").text
    for fragment in (
        'id="provider-status-section"',
        'id="provider-name"',
        'id="provider-model"',
        'id="provider-configured"',
        'id="check-provider"',
        'id="provider-status-message"',
        "/advisory/provider/status",
        "checkProviderStatus",
        "renderProviderStatus",
    ):
        assert fragment in body, f"missing provider status fragment {fragment!r}"


def test_dashboard_ledger_renders_via_textContent():
    body = _client().get("/").text
    assert "advisory.ledgerEntry.textContent" in body
    assert "advisory.ledgerStatus.textContent" in body
    assert ".innerHTML" not in body


def test_dashboard_provider_status_renders_via_textContent():
    body = _client().get("/").text
    assert "advisory.providerFields.name.textContent" in body
    assert "advisory.providerFields.message.textContent" in body
    assert ".innerHTML" not in body


def test_dashboard_inputer_renders_via_textContent():
    """Inputer panel JS must use textContent and never innerHTML."""
    body = _client().get("/").text
    assert "renderInputerStatus" in body
    # advisory.source is read into the run body
    assert "source: advisory.source.value" in body
    # safety carry-over: still no innerHTML anywhere
    assert ".innerHTML" not in body


def test_get_report_round_trip():
    client = _client()
    r = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    )
    rid = r.json()["id"]
    r2 = client.get(f"/reports/{rid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == rid


def test_get_report_404():
    client = _client()
    r = client.get("/reports/does-not-exist")
    assert r.status_code == 404


def test_generate_probes_endpoint():
    client = _client()
    r = client.post(
        "/generate_probes",
        json={"claim": "X is true", "argument": "There is no evidence against X, therefore X is true"},
    )
    assert r.status_code == 200
    assert len(r.json()["probes"]) >= 3


def test_score_probe_results_changes_score():
    client = _client()
    base = client.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    ).json()
    r = client.post(
        "/score_probe_results",
        json={
            "claim": "P",
            "argument": "P. Therefore P.",
            "answers": [
                {"question": "What concrete observation or experiment would falsify the claim?",
                 "passed": True, "answer": "running unit test fails"},
            ],
        },
    )
    assert r.status_code == 200
    # answering a probe positively should not lower the score
    assert r.json()["effectiveness_score"] >= base["effectiveness_score"] - 0.1


def test_health():
    assert _client().get("/health").json()["status"] == "ok"


def test_input_validation_rejects_empty_claim():
    client = _client()
    r = client.post("/evaluate_argument", json={"claim": "", "argument": "P. Therefore P."})
    assert r.status_code == 422


def test_score_probe_results_validation_rejects_empty_claim():
    client = _client()
    r = client.post(
        "/score_probe_results",
        json={"claim": "", "argument": "P. Therefore P.", "answers": []},
    )
    assert r.status_code == 422


def test_file_store_persists_across_app_recreation(tmp_path):
    """Reports written via one app instance are readable from a fresh one
    when both share a FileStore root."""
    from fastapi.testclient import TestClient

    from src.effective_boolean_filter.api import create_app
    from src.effective_boolean_filter.storage import FileStore

    root = tmp_path / "reports"

    # First app: write a report.
    app1 = create_app(store=FileStore(root))
    c1 = TestClient(app1)
    posted = c1.post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P."},
    )
    assert posted.status_code == 200
    rid = posted.json()["id"]

    # Second app, fresh in-memory state, same FileStore root.
    app2 = create_app(store=FileStore(root))
    c2 = TestClient(app2)
    fetched = c2.get(f"/reports/{rid}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == rid
    assert fetched.json()["effective_polarity"] == posted.json()["effective_polarity"]


def test_invalid_report_id_returns_400():
    client = _client()
    r = client.get("/reports/..%2Fescape")  # encoded "../escape"
    # Either 400 (caught by store) or 404 (FastAPI path matching) — both are safe.
    assert r.status_code in (400, 404)


def test_dashboard_template_lives_alongside_module():
    """The dashboard template is shipped as a sibling file to dashboard.py
    so packagers / Docker copies pick it up automatically. If the file is
    moved or accidentally excluded, this test fails before a 500 ever
    reaches a user."""
    from pathlib import Path

    from src.effective_boolean_filter import dashboard as dash

    template = Path(dash.__file__).with_name("dashboard_template.html")
    assert template.is_file(), f"missing dashboard template at {template}"
    contents = template.read_text(encoding="utf-8")
    assert contents.startswith("<!doctype html>")
    assert "__CSP_NONCE__" in contents
    # back-compat: existing callers grep ``DASHBOARD_HTML`` from this module
    assert dash.DASHBOARD_HTML == contents


def test_render_dashboard_html_rejects_self_referential_nonce():
    """A nonce containing the placeholder would replace itself recursively
    and produce broken HTML. The render helper makes that misuse visible."""
    from src.effective_boolean_filter.dashboard import render_dashboard_html

    with pytest.raises(ValueError, match="placeholder"):
        render_dashboard_html("prefix__CSP_NONCE__suffix")
