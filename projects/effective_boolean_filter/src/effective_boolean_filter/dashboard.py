"""Render the dashboard HTML.

The template itself lives in :file:`dashboard_template.html` so that
edits to the markup, CSS, or JS produce reviewable diffs instead of
buried changes inside a multi-thousand-line Python triple-quoted
string. This module is the substitution + caching layer; the security
contract (CSP nonce, ``textContent``-only rendering, no inline event
handlers) is enforced by the security middleware and the dashboard
tests in :mod:`tests.test_api`.
"""
from __future__ import annotations

from pathlib import Path


_TEMPLATE_PATH = Path(__file__).with_name("dashboard_template.html")
# Per-process cache. The template is static at runtime; reading it once
# at import time avoids a filesystem hit on every dashboard render and
# makes a missing template a visible import-time error rather than a
# 500 the first time someone opens the page.
_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")

# Back-compat alias: callers (and existing tests via grep) still expect
# ``DASHBOARD_HTML`` to be importable from this module.
DASHBOARD_HTML = _TEMPLATE


def render_dashboard_html(nonce: str) -> str:
    """Return the dashboard HTML with the per-response CSP nonce filled in.

    Every ``__CSP_NONCE__`` placeholder in the template is replaced. A
    nonce containing the placeholder substring would be self-referential,
    so the small guard below makes that misuse visible rather than
    silently producing broken HTML.
    """
    if "__CSP_NONCE__" in nonce:
        raise ValueError("nonce must not contain the placeholder substring")
    return _TEMPLATE.replace("__CSP_NONCE__", nonce)
