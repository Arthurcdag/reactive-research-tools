"""In-process cache for outputer and inputer responses.

The outputer cache is keyed by
``(prompt_version, provider, model, report_hash, recipe_hash, style)``.
The inputer cache uses a **separate** key shape:
``(prompt_version, provider, model, seed_hash, context_hash, strictness,
count, pool_size)``. Reusing the outputer key shape for inputer would
require pretending seed data was a report — explicitly forbidden by the
inputer V1 spec, so the shapes are distinct dataclasses.

The cache stores the **validated** output dict only — never the raw
provider response — so even a cache hit cannot introduce a malformed
payload.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Protocol


class CacheKeyLike(Protocol):
    """Anything that knows how to render itself as a stable string key."""

    def to_string(self) -> str: ...


@dataclass(frozen=True)
class CacheKey:
    """Outputer cache key (Nyahlothep)."""

    prompt_version: str
    provider: str
    model: str
    report_hash: str
    recipe_hash: str
    style: str

    def to_string(self) -> str:
        return (
            f"{self.prompt_version}|{self.provider}|{self.model}|"
            f"{self.report_hash}|{self.recipe_hash}|{self.style}"
        )


@dataclass(frozen=True)
class InputerCacheKey:
    """Azatoth inputer cache key.

    Distinct shape from :class:`CacheKey` so seed input is never confused
    with a report. The leading ``inputer/`` namespace in
    ``to_string`` ensures string-level isolation between the two key
    families even if both ever shared the same backing store.
    """

    prompt_version: str
    provider: str
    model: str
    seed_hash: str
    context_hash: str
    strictness: str
    count: int
    pool_size: int

    def to_string(self) -> str:
        return (
            f"inputer/{self.prompt_version}|{self.provider}|{self.model}|"
            f"{self.seed_hash}|{self.context_hash}|{self.strictness}|"
            f"count={self.count}|pool={self.pool_size}"
        )


def _stable_hash(obj: object) -> str:
    """Deterministic short hash for any JSON-serialisable object."""
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _stable_string_hash(value: str) -> str:
    encoded = value.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def derive_cache_key(
    *,
    prompt_version: str,
    provider: str,
    model: str,
    selected_report: dict[str, Any],
    replication_recipe: dict[str, Any],
    style: str,
) -> CacheKey:
    return CacheKey(
        prompt_version=prompt_version,
        provider=provider,
        model=model,
        report_hash=_stable_hash(selected_report),
        recipe_hash=_stable_hash(replication_recipe),
        style=style,
    )


def derive_inputer_cache_key(
    *,
    prompt_version: str,
    provider: str,
    model: str,
    seed: str,
    context: str,
    strictness: str,
    count: int,
    pool_size: int,
) -> InputerCacheKey:
    return InputerCacheKey(
        prompt_version=prompt_version,
        provider=provider,
        model=model,
        seed_hash=_stable_string_hash(seed),
        context_hash=_stable_string_hash(context),
        strictness=strictness,
        count=count,
        pool_size=pool_size,
    )


class LLMResponseCache:
    """Thread-safe in-memory store of validated LLM responses.

    Accepts any object exposing ``to_string()`` so both
    :class:`CacheKey` and :class:`InputerCacheKey` work without changes.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: CacheKeyLike) -> Any:
        with self._lock:
            value = self._data.get(key.to_string())
            return copy.deepcopy(value) if value is not None else None

    def put(self, key: CacheKeyLike, value: Any) -> None:
        with self._lock:
            self._data[key.to_string()] = copy.deepcopy(value)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_default_cache = LLMResponseCache()


def get_default_cache() -> LLMResponseCache:
    """Module-level cache used when callers do not pass one explicitly.

    Tests should construct their own :class:`LLMResponseCache` instances
    to avoid leaking state across cases.
    """
    return _default_cache
