"""Nyahlothep outputer: paraphrase a deterministic verdict into validated JSON.

Failure policy (per developer brief):

* Provider unavailable, JSON parse error, schema mismatch, missing
  ``source_report_id`` match, or timeout all surface as exceptions.
  There is no silent fallback to generated prose.
* The outputer never mutates the selected report. The verdict
  (``effective_polarity``, scores, issues, selected candidate) is
  read-only here.

Cache contract: a cache hit avoids any provider call and returns the
previously validated payload. The cache stores validated output only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .llm_cache import (
    LLMResponseCache,
    derive_cache_key,
    get_default_cache,
)
from .llm_client import (
    LLMClient,
    LLMRequest,
    get_client,
)
from .llm_prompts import PROMPT_VERSION, STYLES, Style, render_prompt


MODE = "contract_v0_outputer"

REQUIRED_FIELDS: tuple[str, ...] = (
    "summary",
    "why_selected",
    "replication_steps",
    "caveats",
    "source_report_id",
)

MAX_SUMMARY_CHARS = 2000
MAX_WHY_CHARS = 2000
MAX_STEP_CHARS = 1000
MAX_CAVEAT_CHARS = 1000
MAX_STEPS = 20
MAX_CAVEATS = 20


class OutputerValidationError(ValueError):
    """LLM output failed JSON parsing or schema validation."""


@dataclass(frozen=True)
class OutputerResult:
    mode: str
    provider: str
    model: str
    cache_key: str
    cached: bool
    validated_output: dict[str, Any]


def _check_str(name: str, value: Any, *, max_len: int) -> str:
    if not isinstance(value, str):
        raise OutputerValidationError(f"{name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise OutputerValidationError(f"{name} must be a non-empty string")
    if len(value) > max_len:
        raise OutputerValidationError(
            f"{name} exceeds maximum length ({len(value)} > {max_len})"
        )
    return value


def _check_list_of_str(
    name: str,
    value: Any,
    *,
    min_len: int,
    max_len: int,
    item_max: int,
) -> list[str]:
    if not isinstance(value, list):
        raise OutputerValidationError(f"{name} must be a list of strings")
    if len(value) < min_len:
        raise OutputerValidationError(f"{name} must have at least {min_len} entries")
    if len(value) > max_len:
        raise OutputerValidationError(
            f"{name} has too many entries ({len(value)} > {max_len})"
        )
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise OutputerValidationError(
                f"{name}[{i}] must be a non-empty string"
            )
        if len(item) > item_max:
            raise OutputerValidationError(
                f"{name}[{i}] exceeds maximum length ({len(item)} > {item_max})"
            )
        out.append(item)
    return out


def validate_outputer_payload(
    payload: Any,
    *,
    expected_report_id: str,
) -> dict[str, Any]:
    """Strict schema check. Raises :class:`OutputerValidationError` on any
    mismatch.

    The returned dict is a fresh copy of the validated fields, so callers
    can mutate it without poisoning a cache entry.
    """
    if not isinstance(payload, dict):
        raise OutputerValidationError("LLM output must be a JSON object")
    missing = [f for f in REQUIRED_FIELDS if f not in payload]
    if missing:
        raise OutputerValidationError(
            f"missing required fields: {sorted(missing)}"
        )
    extra = sorted(k for k in payload if k not in REQUIRED_FIELDS)
    if extra:
        raise OutputerValidationError(f"unexpected fields: {extra}")

    summary = _check_str("summary", payload["summary"], max_len=MAX_SUMMARY_CHARS)
    why_selected = _check_str(
        "why_selected", payload["why_selected"], max_len=MAX_WHY_CHARS
    )
    replication_steps = _check_list_of_str(
        "replication_steps",
        payload["replication_steps"],
        min_len=1,
        max_len=MAX_STEPS,
        item_max=MAX_STEP_CHARS,
    )
    # caveats may be empty
    if not isinstance(payload["caveats"], list):
        raise OutputerValidationError("caveats must be a list of strings")
    if len(payload["caveats"]) > MAX_CAVEATS:
        raise OutputerValidationError(
            f"caveats has too many entries ({len(payload['caveats'])} > {MAX_CAVEATS})"
        )
    caveats: list[str] = []
    for i, c in enumerate(payload["caveats"]):
        if not isinstance(c, str) or not c.strip():
            raise OutputerValidationError(f"caveats[{i}] must be a non-empty string")
        if len(c) > MAX_CAVEAT_CHARS:
            raise OutputerValidationError(
                f"caveats[{i}] exceeds maximum length ({len(c)} > {MAX_CAVEAT_CHARS})"
            )
        caveats.append(c)

    source_report_id = payload["source_report_id"]
    if not isinstance(source_report_id, str):
        raise OutputerValidationError("source_report_id must be a string")
    if source_report_id != expected_report_id:
        raise OutputerValidationError(
            f"source_report_id mismatch: got {source_report_id!r}, "
            f"expected {expected_report_id!r}"
        )

    return {
        "summary": summary,
        "why_selected": why_selected,
        "replication_steps": replication_steps,
        "caveats": caveats,
        "source_report_id": source_report_id,
    }


def generate_outputer(
    *,
    selected_report: dict[str, Any],
    replication_recipe: dict[str, Any],
    style: Style,
    client: LLMClient | None = None,
    cache: LLMResponseCache | None = None,
) -> OutputerResult:
    """Generate, validate, and cache a Nyahlothep outputer response.

    Inputs are treated as immutable; this function never mutates either
    ``selected_report`` or ``replication_recipe``.
    """
    if style not in STYLES:
        raise OutputerValidationError(f"unknown style: {style!r}")
    if not isinstance(selected_report, dict) or "id" not in selected_report:
        raise OutputerValidationError(
            "selected_report must be a dict with an 'id' field"
        )
    if not isinstance(replication_recipe, dict):
        raise OutputerValidationError("replication_recipe must be a dict")

    expected_report_id = selected_report["id"]
    if not isinstance(expected_report_id, str) or not expected_report_id:
        raise OutputerValidationError(
            "selected_report.id must be a non-empty string"
        )

    client = client if client is not None else get_client()
    cache = cache if cache is not None else get_default_cache()

    key = derive_cache_key(
        prompt_version=PROMPT_VERSION,
        provider=client.provider,
        model=client.model,
        selected_report=selected_report,
        replication_recipe=replication_recipe,
        style=style,
    )

    cached_value = cache.get(key)
    if cached_value is not None:
        return OutputerResult(
            mode=MODE,
            provider=client.provider,
            model=client.model,
            cache_key=key.to_string(),
            cached=True,
            validated_output=cached_value,
        )

    system, user = render_prompt(
        selected_report=selected_report,
        replication_recipe=replication_recipe,
        style=style,
    )
    request = LLMRequest(
        system=system,
        user=user,
        prompt_version=PROMPT_VERSION,
        style=style,
    )
    response = client.generate(request)

    try:
        parsed = json.loads(response.raw_text)
    except json.JSONDecodeError as exc:
        raise OutputerValidationError(
            f"LLM output is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"
        ) from exc

    validated = validate_outputer_payload(
        parsed, expected_report_id=expected_report_id
    )
    cache.put(key, validated)

    return OutputerResult(
        mode=MODE,
        provider=response.provider,
        model=response.model,
        cache_key=key.to_string(),
        cached=False,
        validated_output=validated,
    )


def outputer_result_to_dict(result: OutputerResult) -> dict[str, Any]:
    return {
        "mode": result.mode,
        "provider": result.provider,
        "model": result.model,
        "cache_key": result.cache_key,
        "cached": result.cached,
        "validated_output": result.validated_output,
    }
