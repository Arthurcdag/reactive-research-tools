"""Azatoth inputer: bounded monkey/typewriter candidate-pool generation.

Failure policy (per inputer V1 brief):

* Provider unavailable, JSON parse error, schema mismatch, missing
  fields, wrong types, over-length values, or insufficient unique
  candidates after dedupe all surface as exceptions.
  There is no silent fallback to a deterministic generator and no
  retry that masks a malformed payload.
* The inputer never mutates the caller's seed/context strings. Cache
  reads/writes go through ``LLMResponseCache``'s deep-copy contract.
* The deterministic engine remains the only verdict source; this
  module only proposes candidates. Selection still flows through
  ``run_nyahlothep_on_candidates``.

Bounds:

* ``count`` is 1..20 (matches the existing wrapper).
* ``pool_size`` defaults to ``min(max(count * 4, 16), 80)`` and is
  clamped to ``[count, 80]``. The provider is asked to emit at least
  ``pool_size`` candidates so that, after dedupe, at least ``count``
  remain.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .advisory import AdvisoryCandidate
from .llm_cache import (
    LLMResponseCache,
    derive_inputer_cache_key,
    get_default_cache,
)
from .llm_client import (
    LLMClient,
    LLMRequest,
    get_client,
)
from .llm_prompts import INPUTER_PROMPT_VERSION, render_inputer_prompt


MODE = "contract_v0_inputer"
COUNT_MIN = 1
COUNT_MAX = 20
POOL_HARD_MAX = 80
POOL_SOFT_FLOOR = 16
POOL_FACTOR = 4

CANDIDATE_REQUIRED_FIELDS: tuple[str, ...] = (
    "candidate_id",
    "claim",
    "argument",
    "context",
    "strictness",
    "template",
    "mutation_notes",
)
VALID_STRICTNESS = {"low", "medium", "high"}

MAX_CLAIM_CHARS = 4000
MAX_ARGUMENT_CHARS = 8000
MAX_CONTEXT_CHARS = 2000
MAX_CANDIDATE_ID_CHARS = 120
MAX_TEMPLATE_CHARS = 120
MAX_MUTATION_NOTES_CHARS = 1000


class InputerValidationError(ValueError):
    """LLM output failed parsing, schema validation, or dedupe sufficiency."""


@dataclass(frozen=True)
class InputerResult:
    mode: str
    provider: str
    model: str
    cache_key: str
    cached: bool
    pool_size: int
    valid_count: int
    deduped_count: int
    azatoth_candidates: list[AdvisoryCandidate]


def default_pool_size(count: int) -> int:
    """Spec rule: ``min(max(count * 4, 16), 80)``."""
    return min(max(count * POOL_FACTOR, POOL_SOFT_FLOOR), POOL_HARD_MAX)


def _check_count(count: int) -> int:
    if not isinstance(count, int) or isinstance(count, bool):
        raise InputerValidationError("count must be an int")
    if count < COUNT_MIN or count > COUNT_MAX:
        raise InputerValidationError(
            f"count must be between {COUNT_MIN} and {COUNT_MAX} (got {count})"
        )
    return count


def _check_pool_size(pool_size: int | None, count: int) -> int:
    if pool_size is None:
        return default_pool_size(count)
    if not isinstance(pool_size, int) or isinstance(pool_size, bool):
        raise InputerValidationError("pool_size must be an int")
    if pool_size < count:
        raise InputerValidationError(
            f"pool_size ({pool_size}) must be >= count ({count})"
        )
    if pool_size > POOL_HARD_MAX:
        raise InputerValidationError(
            f"pool_size ({pool_size}) exceeds hard maximum {POOL_HARD_MAX}"
        )
    return pool_size


def _check_seed(seed: str) -> str:
    if not isinstance(seed, str) or not seed.strip():
        raise InputerValidationError("seed must be a non-empty string")
    if len(seed) > MAX_CLAIM_CHARS:
        raise InputerValidationError(
            f"seed exceeds maximum length ({len(seed)} > {MAX_CLAIM_CHARS})"
        )
    return seed


def _check_context(context: str) -> str:
    if not isinstance(context, str):
        raise InputerValidationError("context must be a string")
    if len(context) > MAX_CONTEXT_CHARS:
        raise InputerValidationError(
            f"context exceeds maximum length ({len(context)} > {MAX_CONTEXT_CHARS})"
        )
    return context


def _check_strictness(strictness: str) -> str:
    if strictness not in VALID_STRICTNESS:
        raise InputerValidationError(
            f"strictness must be one of {sorted(VALID_STRICTNESS)} (got {strictness!r})"
        )
    return strictness


def _validate_candidate_dict(
    payload: Any,
    *,
    expected_strictness: str,
    seen_ids: set[str],
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise InputerValidationError("each candidate must be a JSON object")
    missing = [f for f in CANDIDATE_REQUIRED_FIELDS if f not in payload]
    if missing:
        raise InputerValidationError(
            f"candidate is missing required fields: {sorted(missing)}"
        )
    extra = sorted(k for k in payload if k not in CANDIDATE_REQUIRED_FIELDS)
    if extra:
        raise InputerValidationError(f"candidate has unexpected fields: {extra}")

    cid = payload["candidate_id"]
    if not isinstance(cid, str) or not cid.strip():
        raise InputerValidationError("candidate_id must be a non-empty string")
    if len(cid) > MAX_CANDIDATE_ID_CHARS:
        raise InputerValidationError(
            f"candidate_id exceeds {MAX_CANDIDATE_ID_CHARS} chars"
        )
    if cid in seen_ids:
        raise InputerValidationError(f"duplicate candidate_id in pool: {cid!r}")
    seen_ids.add(cid)

    claim = payload["claim"]
    if not isinstance(claim, str) or not claim.strip():
        raise InputerValidationError("claim must be a non-empty string")
    if len(claim) > MAX_CLAIM_CHARS:
        raise InputerValidationError(
            f"claim exceeds {MAX_CLAIM_CHARS} chars (candidate {cid!r})"
        )

    argument = payload["argument"]
    if not isinstance(argument, str) or not argument.strip():
        raise InputerValidationError("argument must be a non-empty string")
    if len(argument) > MAX_ARGUMENT_CHARS:
        raise InputerValidationError(
            f"argument exceeds {MAX_ARGUMENT_CHARS} chars (candidate {cid!r})"
        )

    context = payload["context"]
    if not isinstance(context, str):
        raise InputerValidationError(
            f"context must be a string (candidate {cid!r})"
        )
    if len(context) > MAX_CONTEXT_CHARS:
        raise InputerValidationError(
            f"context exceeds {MAX_CONTEXT_CHARS} chars (candidate {cid!r})"
        )

    strictness = payload["strictness"]
    if strictness not in VALID_STRICTNESS:
        raise InputerValidationError(
            f"strictness must be one of {sorted(VALID_STRICTNESS)} "
            f"(candidate {cid!r}, got {strictness!r})"
        )
    if strictness != expected_strictness:
        raise InputerValidationError(
            f"candidate strictness {strictness!r} does not match request "
            f"strictness {expected_strictness!r} (candidate {cid!r})"
        )

    template = payload["template"]
    if not isinstance(template, str) or not template.strip():
        raise InputerValidationError(
            f"template must be a non-empty string (candidate {cid!r})"
        )
    if len(template) > MAX_TEMPLATE_CHARS:
        raise InputerValidationError(
            f"template exceeds {MAX_TEMPLATE_CHARS} chars (candidate {cid!r})"
        )

    mutation_notes = payload["mutation_notes"]
    if not isinstance(mutation_notes, str):
        raise InputerValidationError(
            f"mutation_notes must be a string (candidate {cid!r})"
        )
    if len(mutation_notes) > MAX_MUTATION_NOTES_CHARS:
        raise InputerValidationError(
            f"mutation_notes exceeds {MAX_MUTATION_NOTES_CHARS} chars (candidate {cid!r})"
        )

    return {
        "candidate_id": cid,
        "claim": claim,
        "argument": argument,
        "context": context,
        "strictness": strictness,
        "template": template,
        "mutation_notes": mutation_notes,
    }


def _dedupe(candidates: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Drop candidates whose (claim, argument) pair already appeared.

    Comparison is case-folded and whitespace-collapsed so trivially-
    rephrased duplicates (extra spaces, casing) do not survive.
    """
    seen_pairs: set[tuple[str, str]] = set()
    keep: list[dict[str, str]] = []
    for c in candidates:
        key = (
            " ".join(c["claim"].casefold().split()),
            " ".join(c["argument"].casefold().split()),
        )
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        keep.append(c)
    return keep


def validate_inputer_payload(
    payload: Any,
    *,
    expected_strictness: str,
) -> list[dict[str, str]]:
    """Strict pool-shape check returning a list of valid dict candidates."""
    if not isinstance(payload, dict):
        raise InputerValidationError("LLM output must be a JSON object")
    extra_top = sorted(k for k in payload if k != "azatoth_candidates")
    if extra_top:
        raise InputerValidationError(f"unexpected top-level fields: {extra_top}")
    if "azatoth_candidates" not in payload:
        raise InputerValidationError(
            "missing required field 'azatoth_candidates'"
        )
    raw = payload["azatoth_candidates"]
    if not isinstance(raw, list):
        raise InputerValidationError("azatoth_candidates must be a list")
    if not raw:
        raise InputerValidationError("azatoth_candidates is empty")
    seen_ids: set[str] = set()
    out: list[dict[str, str]] = []
    for i, c in enumerate(raw):
        try:
            out.append(
                _validate_candidate_dict(
                    c,
                    expected_strictness=expected_strictness,
                    seen_ids=seen_ids,
                )
            )
        except InputerValidationError as exc:
            raise InputerValidationError(
                f"azatoth_candidates[{i}]: {exc}"
            ) from None
    return out


def _to_advisory_candidate(d: dict[str, str]) -> AdvisoryCandidate:
    return AdvisoryCandidate(
        candidate_id=d["candidate_id"],
        claim=d["claim"],
        argument=d["argument"],
        context=d["context"],
        strictness=d["strictness"],  # type: ignore[arg-type]
        template=d["template"],
        mutation_notes=d["mutation_notes"],
    )


def generate_inputer(
    *,
    seed: str,
    context: str,
    count: int,
    strictness: str = "medium",
    pool_size: int | None = None,
    client: LLMClient | None = None,
    cache: LLMResponseCache | None = None,
) -> InputerResult:
    """Generate, validate, dedupe, and slice the Azatoth candidate pool.

    Returns exactly ``count`` validated, unique candidates or raises
    :class:`InputerValidationError`. The wrapper never silently shrinks
    or pads the result.
    """
    seed = _check_seed(seed)
    context = _check_context(context)
    strictness = _check_strictness(strictness)
    count = _check_count(count)
    resolved_pool = _check_pool_size(pool_size, count)

    client = client if client is not None else get_client()
    cache = cache if cache is not None else get_default_cache()

    key = derive_inputer_cache_key(
        prompt_version=INPUTER_PROMPT_VERSION,
        provider=client.provider,
        model=client.model,
        seed=seed,
        context=context,
        strictness=strictness,
        count=count,
        pool_size=resolved_pool,
    )

    cached_value = cache.get(key)
    if cached_value is not None:
        return InputerResult(
            mode=MODE,
            provider=client.provider,
            model=client.model,
            cache_key=key.to_string(),
            cached=True,
            pool_size=resolved_pool,
            valid_count=cached_value["valid_count"],
            deduped_count=cached_value["deduped_count"],
            azatoth_candidates=[
                _to_advisory_candidate(c) for c in cached_value["azatoth_candidates"]
            ],
        )

    system, user = render_inputer_prompt(
        seed=seed,
        context=context,
        count=count,
        pool_size=resolved_pool,
        strictness=strictness,
    )
    request = LLMRequest(
        system=system,
        user=user,
        prompt_version=INPUTER_PROMPT_VERSION,
        # style is unused for the inputer; pass a stable label so cache
        # logic and scripted-test overrides remain explicit.
        style="inputer",
    )
    response = client.generate(request)

    try:
        parsed = json.loads(response.raw_text)
    except json.JSONDecodeError as exc:
        raise InputerValidationError(
            f"LLM output is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"
        ) from exc

    validated = validate_inputer_payload(parsed, expected_strictness=strictness)
    valid_count = len(validated)

    deduped = _dedupe(validated)
    deduped_count = len(deduped)

    if deduped_count < count:
        raise InputerValidationError(
            f"insufficient unique candidates after dedupe: "
            f"got {deduped_count} unique (from {valid_count} valid), need {count}"
        )

    selected = deduped[:count]
    cache_value = {
        "valid_count": valid_count,
        "deduped_count": deduped_count,
        "azatoth_candidates": selected,
    }
    cache.put(key, cache_value)

    return InputerResult(
        mode=MODE,
        provider=response.provider,
        model=response.model,
        cache_key=key.to_string(),
        cached=False,
        pool_size=resolved_pool,
        valid_count=valid_count,
        deduped_count=deduped_count,
        azatoth_candidates=[_to_advisory_candidate(c) for c in selected],
    )


def inputer_result_to_dict(result: InputerResult) -> dict[str, Any]:
    from .advisory import advisory_candidate_to_dict

    return {
        "mode": result.mode,
        "provider": result.provider,
        "model": result.model,
        "cache_key": result.cache_key,
        "cached": result.cached,
        "pool_size": result.pool_size,
        "valid_count": result.valid_count,
        "deduped_count": result.deduped_count,
        "azatoth_candidates": [
            advisory_candidate_to_dict(c) for c in result.azatoth_candidates
        ],
    }
