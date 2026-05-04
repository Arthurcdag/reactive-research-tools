"""LLM client interface, deterministic fake, and provider adapter slot.

The Nyahlothep outputer (and, later, the Azatoth inputer) calls into an
:class:`LLMClient`. V1 ships only the deterministic fake — that keeps the
stack runnable without provider keys and without the V1 PR pinning a
specific SDK version. The real provider adapter slots in behind the same
``EBF_LLM_PROVIDER`` env var.

Design constraints:

* Failure is visible. Provider unavailability, timeouts, and unsupported
  configurations raise typed exceptions. Callers must catch them and
  surface an HTTP error; there is no silent fallback to generated prose.
* User-supplied claim/argument/context text passes through ``LLMRequest``
  as **data**, never as instructions. The system prompt (in
  ``llm_prompts.py``) is the only string the LLM treats as instructions.
* Tests never call a real provider. They construct
  :class:`DeterministicFakeClient` directly and (where needed) supply
  scripted responses.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    prompt_version: str
    style: str
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class LLMResponse:
    raw_text: str
    provider: str
    model: str


class LLMClient(ABC):
    @property
    @abstractmethod
    def provider(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse: ...


class DisabledLLMClientError(RuntimeError):
    """Raised when ``EBF_LLM_PROVIDER`` selects an unavailable backend."""


class LLMProviderUnavailable(RuntimeError):
    """Provider configured but unreachable (network/auth)."""


class LLMTimeoutError(RuntimeError):
    """Provider call exceeded ``LLMRequest.timeout_seconds``."""


class DeterministicFakeClient(LLMClient):
    """Returns canned JSON keyed by style.

    Used in tests and as the default in V1 so the stack runs without
    provider keys. ``scripted`` lets a test override the canned output to
    exercise validation/error paths.
    """

    PROVIDER = "fake-deterministic"
    MODEL = "fake-deterministic-1"

    def __init__(self, *, scripted: Mapping[str, str] | None = None) -> None:
        self._scripted = dict(scripted) if scripted else {}

    @property
    def provider(self) -> str:
        return self.PROVIDER

    @property
    def model(self) -> str:
        return self.MODEL

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.style in self._scripted:
            return LLMResponse(
                raw_text=self._scripted[request.style],
                provider=self.PROVIDER,
                model=self.MODEL,
            )
        try:
            payload = json.loads(request.user)
            report_id = payload.get("selected_report", {}).get("id", "unknown")
        except (json.JSONDecodeError, AttributeError):
            report_id = "unknown"
        stub = {
            "summary": f"Deterministic fake summary for style={request.style}.",
            "why_selected": (
                f"Fake client ran for style {request.style!r}; "
                f"source report {report_id!r}."
            ),
            "replication_steps": [
                "Open the dashboard and run the seed argument.",
                "Inspect the deterministic verdict.",
                "Confirm the selected candidate id matches the run output.",
            ],
            "caveats": [
                "This response is from the deterministic fake client; no provider was called.",
            ],
            "source_report_id": report_id,
        }
        return LLMResponse(
            raw_text=json.dumps(stub),
            provider=self.PROVIDER,
            model=self.MODEL,
        )


def get_client(*, env: Mapping[str, str] | None = None) -> LLMClient:
    """Resolve a client from env. Default is :class:`DeterministicFakeClient`.

    Set ``EBF_LLM_PROVIDER`` to enable a real provider. V1 reserves the
    slot but does not ship a real adapter; selecting any non-fake value
    raises :class:`DisabledLLMClientError` so callers see a visible
    failure rather than a silent stub.
    """
    source = dict(env) if env is not None else dict(os.environ)
    provider = (source.get("EBF_LLM_PROVIDER") or "").strip().lower()
    if not provider or provider == "fake":
        return DeterministicFakeClient()
    raise DisabledLLMClientError(
        f"LLM provider {provider!r} is not available in this build. "
        "Unset EBF_LLM_PROVIDER or set it to 'fake' to use the "
        "deterministic fake client. The real provider adapter ships in "
        "a follow-on PR after the outputer orchestration is stable."
    )
