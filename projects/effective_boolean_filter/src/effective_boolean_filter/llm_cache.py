"""In-process cache for outputer responses.

Keyed by ``(prompt_version, provider, model, report_hash, recipe_hash,
style)`` so distinct prompt versions, distinct providers, and distinct
inputs never collide. The cache stores the **validated** output dict
only — never the raw provider response — so even a cache hit cannot
introduce a malformed payload.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheKey:
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


def _stable_hash(obj: object) -> str:
    """Deterministic short hash for any JSON-serialisable object."""
    encoded = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
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


class LLMResponseCache:
    """Thread-safe in-memory store of validated outputer responses."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: CacheKey) -> dict[str, Any] | None:
        with self._lock:
            value = self._data.get(key.to_string())
            return dict(value) if value is not None else None

    def put(self, key: CacheKey, value: dict[str, Any]) -> None:
        with self._lock:
            self._data[key.to_string()] = dict(value)

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
