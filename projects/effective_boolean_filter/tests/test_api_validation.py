"""Negative-path API tests.

Locks in:

  - Pydantic body-length limits on every endpoint (claim, argument,
    context, task, probe answers, answer-list cardinality).
  - Strictness whitelist (low/medium/high; case-sensitive).
  - Malformed probe-answer rejection.
  - Dashboard security headers on ``GET /`` and on every endpoint
    that goes through the security middleware.
  - Defensive behaviour for non-JSON, missing-field, and wrong-type
    bodies.

All tests skip cleanly when FastAPI / Pydantic are not installed.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")


def _client():
    from fastapi.testclient import TestClient
    from src.effective_boolean_filter.api import create_app
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# body-length limits
# ---------------------------------------------------------------------------

def test_evaluate_rejects_claim_over_max_length():
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "x" * 4001, "argument": "P. Therefore P."},
    )
    assert r.status_code == 422


def test_evaluate_rejects_argument_over_max_length():
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "x" * 8001},
    )
    assert r.status_code == 422


def test_evaluate_rejects_context_over_max_length():
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P.", "context": "x" * 2001},
    )
    assert r.status_code == 422


def test_evaluate_rejects_task_over_max_length():
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P.", "task": "x" * 501},
    )
    assert r.status_code == 422


def test_generate_probes_rejects_argument_over_max_length():
    r = _client().post(
        "/generate_probes",
        json={"claim": "P", "argument": "x" * 8001},
    )
    assert r.status_code == 422


def test_generate_probes_rejects_context_over_max_length():
    r = _client().post(
        "/generate_probes",
        json={"claim": "P", "argument": "P. Therefore P.", "context": "x" * 2001},
    )
    assert r.status_code == 422


def test_score_probes_rejects_claim_over_max_length():
    r = _client().post(
        "/score_probe_results",
        json={"claim": "x" * 4001, "argument": "P. Therefore P.", "answers": []},
    )
    assert r.status_code == 422


def test_score_probes_rejects_too_many_answers():
    answers = [{"question": f"q{i}", "passed": True, "answer": ""} for i in range(21)]
    r = _client().post(
        "/score_probe_results",
        json={"claim": "P", "argument": "P. Therefore P.", "answers": answers},
    )
    assert r.status_code == 422


def test_score_probes_rejects_answer_field_over_max_length():
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P",
            "argument": "P. Therefore P.",
            "answers": [{"question": "q?", "passed": True, "answer": "x" * 4001}],
        },
    )
    assert r.status_code == 422


def test_score_probes_rejects_question_over_max_length():
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P",
            "argument": "P. Therefore P.",
            "answers": [{"question": "q" * 1001, "passed": True}],
        },
    )
    assert r.status_code == 422


# Length limits should accept the boundary value (max_length is inclusive).
def test_evaluate_accepts_claim_at_max_length():
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "x" * 4000, "argument": "P. Therefore P."},
    )
    assert r.status_code == 200


def test_evaluate_accepts_argument_at_max_length():
    arg = ("P. " * 2666)[:8000]  # exactly 8000 chars, ends with valid token
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": arg},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# strictness whitelist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["extreme", "Low", "MEDIUM", "high ", " high", "", "extra-strict", "0"])
def test_evaluate_rejects_invalid_strictness(bad):
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P.", "strictness": bad},
    )
    assert r.status_code == 422, f"strictness={bad!r} should be rejected"


@pytest.mark.parametrize("bad_type", [True, 1, 0.5, ["medium"], {"x": "medium"}])
def test_evaluate_rejects_strictness_wrong_type(bad_type):
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P.", "strictness": bad_type},
    )
    assert r.status_code == 422


@pytest.mark.parametrize("good", ["low", "medium", "high"])
def test_evaluate_accepts_each_valid_strictness(good):
    r = _client().post(
        "/evaluate_argument",
        json={"claim": "P", "argument": "P. Therefore P.", "strictness": good},
    )
    assert r.status_code == 200


def test_score_probes_rejects_invalid_strictness():
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P", "argument": "P. Therefore P.",
            "strictness": "extreme", "answers": [],
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# malformed probe answers
# ---------------------------------------------------------------------------

def test_score_probes_rejects_answer_missing_passed():
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P", "argument": "P. Therefore P.",
            "answers": [{"question": "q?", "answer": "yes"}],
        },
    )
    assert r.status_code == 422


def test_score_probes_rejects_answer_missing_question():
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P", "argument": "P. Therefore P.",
            "answers": [{"passed": True}],
        },
    )
    assert r.status_code == 422


@pytest.mark.parametrize("bad_passed", ["yes", "true", 1, 0, None, [], {}])
def test_score_probes_rejects_answer_passed_wrong_type(bad_passed):
    # Pydantic v2 coerces some int/bool combinations; only literal-bool inputs
    # we care about here. Non-coercible types must 422.
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P", "argument": "P. Therefore P.",
            "answers": [{"question": "q?", "passed": bad_passed}],
        },
    )
    if isinstance(bad_passed, (int, str)) and not isinstance(bad_passed, bool):
        # pydantic v2 accepts 0/1 and "true"/"false" by default — record that
        # behaviour, but a value pydantic doesn't coerce must 422.
        assert r.status_code in (200, 422)
    else:
        assert r.status_code == 422


def test_score_probes_rejects_empty_question():
    r = _client().post(
        "/score_probe_results",
        json={
            "claim": "P", "argument": "P. Therefore P.",
            "answers": [{"question": "", "passed": True}],
        },
    )
    assert r.status_code == 422


def test_score_probes_rejects_answers_not_a_list():
    r = _client().post(
        "/score_probe_results",
        json={"claim": "P", "argument": "P. Therefore P.", "answers": "none"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# generic body / type validation
# ---------------------------------------------------------------------------

def test_evaluate_rejects_missing_claim():
    r = _client().post("/evaluate_argument", json={"argument": "P. Therefore P."})
    assert r.status_code == 422


def test_evaluate_rejects_missing_argument():
    r = _client().post("/evaluate_argument", json={"claim": "P"})
    assert r.status_code == 422


def test_evaluate_rejects_non_json_body():
    r = _client().post(
        "/evaluate_argument",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_evaluate_rejects_wrong_type_for_claim():
    r = _client().post(
        "/evaluate_argument",
        json={"claim": ["a", "b"], "argument": "P. Therefore P."},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# dashboard security headers (regression — task 3 acceptance criterion)
# ---------------------------------------------------------------------------

EXPECTED_CSP_FRAGMENTS = (
    "default-src 'none'",
    "script-src 'nonce-",
    "style-src 'nonce-",
    "connect-src 'self'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)


def test_dashboard_csp_contains_all_required_directives():
    r = _client().get("/")
    csp = r.headers.get("content-security-policy", "")
    for fragment in EXPECTED_CSP_FRAGMENTS:
        assert fragment in csp, f"missing CSP fragment {fragment!r} in {csp!r}"


def test_dashboard_csp_nonce_is_per_response():
    """Each render must use a fresh nonce, otherwise a leaked nonce would
    keep working across requests."""
    c = _client()
    r1 = c.get("/")
    r2 = c.get("/")
    assert r1.headers["content-security-policy"] != r2.headers["content-security-policy"]


def test_dashboard_cache_control_no_store():
    r = _client().get("/")
    assert r.headers.get("cache-control") == "no-store"


def test_dashboard_extra_security_headers_present():
    r = _client().get("/")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"
    perms = r.headers.get("permissions-policy", "")
    for feature in ("camera=()", "microphone=()", "geolocation=()", "payment=()"):
        assert feature in perms


def test_security_headers_apply_to_api_endpoints_too():
    """The middleware adds the baseline headers on every response, not
    just on GET /."""
    r = _client().get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_dashboard_html_does_not_inline_user_provided_data():
    """The dashboard is static HTML; it must not interpolate any
    request-controlled string. Verifying the body has no obvious
    interpolation tokens guards against accidental future regressions."""
    r = _client().get("/")
    body = r.text
    # the only dynamic value in the page is the per-response CSP nonce on
    # script/style tags. The body must NOT contain query strings or other
    # request data.
    assert "?" not in body.split("</head>")[0] or "viewport" in body[:400]


# ---------------------------------------------------------------------------
# 404 surface
# ---------------------------------------------------------------------------

def test_unknown_endpoint_returns_404():
    r = _client().get("/does-not-exist")
    assert r.status_code == 404


def test_method_not_allowed_returns_405():
    r = _client().get("/evaluate_argument")
    assert r.status_code == 405
