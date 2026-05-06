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
        # scripted overrides take precedence so tests can exercise error paths.
        # Keyed by style for the outputer; keyed by prompt_version + style or
        # by prompt_version alone for the inputer (style is not used there).
        for key in (request.style, request.prompt_version,
                    f"{request.prompt_version}:{request.style}"):
            if key and key in self._scripted:
                return LLMResponse(
                    raw_text=self._scripted[key],
                    provider=self.PROVIDER,
                    model=self.MODEL,
                )

        # Branch on prompt_version. Any future prompt family adds a new
        # branch here; the default outputer branch stays unchanged.
        if request.prompt_version == "azatoth_inputer_v1":
            raw_text = self._render_inputer_pool(request.user)
        else:
            raw_text = self._render_outputer_stub(request.user, request.style)

        return LLMResponse(
            raw_text=raw_text,
            provider=self.PROVIDER,
            model=self.MODEL,
        )

    @staticmethod
    def _render_outputer_stub(user_message: str, style: str) -> str:
        try:
            payload = json.loads(user_message)
            report_id = payload.get("selected_report", {}).get("id", "unknown")
        except (json.JSONDecodeError, AttributeError):
            report_id = "unknown"
        stub = {
            "summary": f"Deterministic fake summary for style={style}.",
            "why_selected": (
                f"Fake client ran for style {style!r}; "
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
        return json.dumps(stub)

    # Deterministic monkey/typewriter pool for the Azatoth inputer.
    # Sixteen rhetorical templates × up to five mutation cycles cover the
    # full pool_size range (1..80). Each (template, cycle) combination
    # yields a unique (claim, argument) pair so the wrapper's dedupe step
    # leaves the pool intact unless a test deliberately injects duplicates.
    _INPUTER_TEMPLATES: tuple[tuple[str, str, str], ...] = (
        # (template_name, claim_form, argument_form)
        # Use {seed} for substitution. The argument_form may use {seed}
        # multiple times.
        (
            "clean_double_negation",
            "{seed}",
            "It is not the case that not {seed}. Therefore {seed}.",
        ),
        (
            "double_negation_paraphrase",
            "{seed}",
            "Not not {seed}. Therefore {seed}.",
        ),
        (
            "not_false_paraphrase",
            "{seed}",
            "{seed} is not false. Therefore {seed}.",
        ),
        (
            "epistemic_absence",
            "{seed}",
            "There is no evidence against {seed}. Therefore {seed}.",
        ),
        (
            "no_one_disproved",
            "{seed}",
            "No one has disproved {seed}. Therefore {seed}.",
        ),
        (
            "simulation_to_production",
            "{seed} works in production",
            "{seed} works in simulation. Therefore {seed} works in production.",
        ),
        (
            "legal_to_physical",
            "{seed} is physically possible",
            "{seed} is not legally impossible. Therefore {seed} is physically possible.",
        ),
        (
            "possibility_to_actuality",
            "{seed} is true",
            "{seed} is possible in theory. Therefore {seed} is true.",
        ),
        (
            "fallacy_fallacy",
            "{seed} is false",
            "The argument for {seed} is a weak argument. Therefore {seed} is false.",
        ),
        (
            "explains_everything",
            "{seed}",
            "{seed} explains everything we observe. Therefore {seed}.",
        ),
        (
            "appeal_to_intuition",
            "{seed}",
            "{seed} feels intuitively right. Therefore {seed}.",
        ),
        (
            "consistent_with_data",
            "{seed} is correct",
            "{seed} is consistent with our data. Therefore {seed} is correct.",
        ),
        (
            "many_studies",
            "{seed}",
            "Many studies report findings consistent with {seed}. Therefore {seed}.",
        ),
        (
            "literal_yes",
            "{seed}",
            "{seed}. Therefore {seed}.",
        ),
        (
            "sample_to_scale",
            "{seed} scales to a million users",
            "{seed} passed a small sample. Therefore {seed} scales to a million users.",
        ),
        (
            "non_implication",
            "{seed} follows",
            "{seed} does not imply deployment readiness. Therefore deployment readiness follows.",
        ),
    )

    @classmethod
    def _render_inputer_pool(cls, user_message: str) -> str:
        try:
            payload = json.loads(user_message)
        except json.JSONDecodeError:
            payload = {}
        seed_raw = payload.get("seed", "P")
        seed = (seed_raw if isinstance(seed_raw, str) else "P").strip() or "P"
        context = payload.get("context", "") or ""
        if not isinstance(context, str):
            context = ""
        strictness = payload.get("strictness", "medium")
        if strictness not in ("low", "medium", "high"):
            strictness = "medium"
        pool_size_raw = payload.get("pool_size", 16)
        try:
            pool_size = max(1, min(80, int(pool_size_raw)))
        except (TypeError, ValueError):
            pool_size = 16

        templates = cls._INPUTER_TEMPLATES
        candidates: list[dict[str, str]] = []
        for idx in range(pool_size):
            template_name, claim_form, argument_form = templates[idx % len(templates)]
            cycle = idx // len(templates)
            mutation_suffix = ""
            if cycle:
                mutation_suffix = f" (variant {cycle + 1})"
            candidates.append(
                {
                    "candidate_id": f"cand_{idx + 1:03d}_{template_name}",
                    "claim": claim_form.format(seed=seed),
                    "argument": (argument_form.format(seed=seed) + mutation_suffix).strip(),
                    "context": context,
                    "strictness": strictness,
                    "template": template_name,
                    "mutation_notes": (
                        f"monkey/typewriter cycle {cycle + 1} of template "
                        f"{template_name!r}"
                    ),
                }
            )
        return json.dumps({"azatoth_candidates": candidates})


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
