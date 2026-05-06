"""LLM client interface, deterministic fake, and Anthropic provider adapter.

The Nyahlothep outputer and Azatoth inputer call into an
:class:`LLMClient`. The deterministic fake remains the default so the stack
runs without provider keys. The live Anthropic adapter is opt-in behind
``EBF_LLM_PROVIDER=anthropic``.

Design constraints:

* Failure is visible. Provider unavailability, timeouts, and unsupported
  configurations raise typed exceptions. Callers must catch them and
  surface an HTTP error; there is no silent fallback to generated prose.
* User-supplied claim/argument/context text passes through ``LLMRequest``
  as **data**, never as instructions. The system prompt (in
  ``llm_prompts.py``) is the only string the LLM treats as instructions.
* Tests never call a real provider. They construct fakes or inject an HTTP
  client into :class:`AnthropicClient`.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


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


class AnthropicClient(LLMClient):
    """Direct Anthropic Messages API adapter using existing httpx."""

    PROVIDER = "anthropic"
    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_VERSION = "2023-06-01"
    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        anthropic_version: str = DEFAULT_VERSION,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        http_client: Any | None = None,
    ) -> None:
        self._api_key = _require_config(api_key, "ANTHROPIC_API_KEY")
        self._model = _require_config(model, "EBF_LLM_MODEL")
        self._anthropic_version = _require_config(
            anthropic_version,
            "EBF_ANTHROPIC_VERSION",
        )
        self._base_url = _require_base_url(base_url)
        self._max_tokens = _require_positive_int(max_tokens, "EBF_LLM_MAX_TOKENS")
        self._http_client = http_client if http_client is not None else httpx.Client()

    @property
    def provider(self) -> str:
        return self.PROVIDER

    @property
    def model(self) -> str:
        return self._model

    def generate(self, request: LLMRequest) -> LLMResponse:
        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._anthropic_version,
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "system": request.system,
            "messages": [
                {"role": "user", "content": request.user},
            ],
        }
        try:
            response = self._http_client.post(
                url,
                headers=headers,
                json=payload,
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Anthropic provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderUnavailable(
                f"Anthropic provider request failed: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise LLMProviderUnavailable(_anthropic_error_message(response))

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderUnavailable(
                "Anthropic provider returned non-JSON response"
            ) from exc

        raw_text = _extract_anthropic_text(data)
        return LLMResponse(
            raw_text=raw_text,
            provider=self.provider,
            model=self.model,
        )


def get_client(*, env: Mapping[str, str] | None = None) -> LLMClient:
    """Resolve a client from env. Default is :class:`DeterministicFakeClient`.

    Set ``EBF_LLM_PROVIDER=anthropic`` to enable the live Anthropic adapter.
    Missing or malformed provider configuration raises
    :class:`DisabledLLMClientError` so callers see a visible failure rather
    than a silent stub.
    """
    source = dict(env) if env is not None else dict(os.environ)
    provider = (source.get("EBF_LLM_PROVIDER") or "").strip().lower()
    if not provider or provider == "fake":
        return DeterministicFakeClient()
    if provider == "anthropic":
        max_tokens = _parse_max_tokens(
            source.get("EBF_LLM_MAX_TOKENS"),
            default=AnthropicClient.DEFAULT_MAX_TOKENS,
        )
        return AnthropicClient(
            api_key=source.get("ANTHROPIC_API_KEY", ""),
            model=source.get("EBF_LLM_MODEL", ""),
            anthropic_version=source.get(
                "EBF_ANTHROPIC_VERSION",
                AnthropicClient.DEFAULT_VERSION,
            ),
            base_url=source.get("EBF_LLM_BASE_URL", AnthropicClient.DEFAULT_BASE_URL),
            max_tokens=max_tokens,
        )
    raise DisabledLLMClientError(
        f"LLM provider {provider!r} is not supported. "
        "Unset EBF_LLM_PROVIDER, set it to 'fake', or set it to 'anthropic'."
    )


def _require_config(value: Any, env_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DisabledLLMClientError(f"{env_name} is required for Anthropic provider")
    return value.strip()


def _require_base_url(value: Any) -> str:
    base_url = _require_config(value, "EBF_LLM_BASE_URL").rstrip("/")
    if not (base_url.startswith("https://") or base_url.startswith("http://")):
        raise DisabledLLMClientError(
            "EBF_LLM_BASE_URL must start with http:// or https://"
        )
    return base_url


def _parse_max_tokens(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return _require_positive_int(int(value), "EBF_LLM_MAX_TOKENS")
    except ValueError as exc:
        raise DisabledLLMClientError(
            "EBF_LLM_MAX_TOKENS must be a positive integer"
        ) from exc


def _require_positive_int(value: Any, env_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DisabledLLMClientError(f"{env_name} must be a positive integer")
    return value


def _anthropic_error_message(response: Any) -> str:
    status = getattr(response, "status_code", "unknown")
    request_id = ""
    headers = getattr(response, "headers", {}) or {}
    if isinstance(headers, Mapping) and headers.get("request-id"):
        request_id = f" request_id={headers['request-id']}"
    try:
        data = response.json()
    except ValueError:
        return f"Anthropic provider returned HTTP {status}.{request_id}"
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        err_type = error.get("type")
        message = error.get("message")
        detail = ": ".join(
            str(part)
            for part in (err_type, message)
            if isinstance(part, str) and part
        )
        if detail:
            return f"Anthropic provider returned HTTP {status}: {detail}.{request_id}"
    return f"Anthropic provider returned HTTP {status}.{request_id}"


def _extract_anthropic_text(data: Any) -> str:
    if not isinstance(data, dict):
        raise LLMProviderUnavailable("Anthropic provider response must be a JSON object")
    content = data.get("content")
    if not isinstance(content, list):
        raise LLMProviderUnavailable(
            "Anthropic provider response missing content list"
        )
    texts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str):
            texts.append(text)
    if not texts:
        raise LLMProviderUnavailable(
            "Anthropic provider response contained no text blocks"
        )
    return "".join(texts)
