"""FastAPI surface for the Effective Boolean Argument Filter (spec Section 11).

Endpoints:
  POST /evaluate_argument
  POST /generate_probes
  POST /score_probe_results
  POST /advisory/azatoth
  POST /advisory/azatoth/input
  POST /advisory/nyahlothep
  POST /advisory/nyahlothep/output
  POST /advisory/run
  GET  /advisory/provider/status
  GET  /advisory/ledger
  GET  /advisory/ledger/{entry_id}
  POST /advisory/ledger/{entry_id}/replay
  GET  /
  GET  /reports/{id}

FastAPI/Pydantic are imported lazily so ``import effective_boolean_filter`` does
not require them; install with ``pip install fastapi uvicorn pydantic`` to
boot the API.
"""
from __future__ import annotations

import secrets
from typing import Any

try:
    from pydantic import BaseModel, Field
    _HAS_PYDANTIC = True
except ImportError:  # pragma: no cover
    _HAS_PYDANTIC = False
    BaseModel = object  # type: ignore[assignment,misc]

from .engine import evaluate_argument
from .commercial import PRIVACY_SUMMARY, TERMS_SUMMARY, plans_payload
from .dashboard import render_dashboard_html
from .operations import (
    FixedWindowRateLimiter,
    authenticate_request,
    content_length_over_limit,
    identity_key,
    is_public_path,
    load_access_config,
)
from .parser import parse_argument, parse_claim
from .probes import generate_probes as gen_probes
from .report import to_json_dict
from .scoring import score_argument
from .storage import ReportStore, get_store
from .advisory_ledger import (
    AdvisoryLedger,
    LedgerCorruptionError,
    LedgerDisabledError,
    LedgerEntryNotFound,
    LedgerError,
    LedgerValidationError,
    get_advisory_ledger,
)
from .advisory import (
    AdvisoryCandidate,
    advisory_candidate_to_dict,
    advisory_run_to_dict,
    azatoth_generate,
    run_advisory_wrapper,
    run_nyahlothep_on_candidates,
)
from .llm_client import (
    DisabledLLMClientError,
    LLMClient,
    LLMProviderUnavailable,
    LLMTimeoutError,
    provider_status,
)
from .llm_outputer import (
    OutputerValidationError,
    generate_outputer,
    outputer_result_to_dict,
)
from .llm_inputer import (
    InputerValidationError,
    generate_inputer,
    inputer_result_to_dict,
)
from .llm_cache import LLMResponseCache
from .trace_gate import PipelineInvariantError


if _HAS_PYDANTIC:

    class EvaluateBody(BaseModel):  # type: ignore[misc]
        claim: str = Field(..., min_length=1, max_length=4000)
        argument: str = Field(..., min_length=1, max_length=8000)
        context: str = Field("", max_length=2000)
        task: str = Field("argument evaluation", max_length=500)
        strictness: str = Field("medium", pattern="^(low|medium|high)$")

    class ProbeBody(BaseModel):  # type: ignore[misc]
        claim: str = Field(..., min_length=1, max_length=4000)
        argument: str = Field(..., min_length=1, max_length=8000)
        context: str = Field("", max_length=2000)

    class ProbeAnswer(BaseModel):  # type: ignore[misc]
        question: str = Field(..., min_length=1, max_length=1000)
        passed: bool
        answer: str = Field("", max_length=4000)

    class ScoreProbesBody(BaseModel):  # type: ignore[misc]
        claim: str = Field(..., min_length=1, max_length=4000)
        argument: str = Field(..., min_length=1, max_length=8000)
        context: str = Field("", max_length=2000)
        strictness: str = Field("medium", pattern="^(low|medium|high)$")
        answers: list[ProbeAnswer] = Field(default_factory=list, max_length=20)

    class AdvisoryGenerateBody(BaseModel):  # type: ignore[misc]
        seed: str = Field(..., min_length=1, max_length=4000)
        context: str = Field("", max_length=2000)
        count: int = Field(8, ge=1, le=20)
        strictness: str = Field("medium", pattern="^(low|medium|high)$")

    class AzatothInputBody(BaseModel):  # type: ignore[misc]
        seed: str = Field(..., min_length=1, max_length=4000)
        context: str = Field("", max_length=2000)
        count: int = Field(8, ge=1, le=20)
        strictness: str = Field("medium", pattern="^(low|medium|high)$")
        # pool_size is optional; the wrapper applies the default rule
        # min(max(count*4, 16), 80) when omitted.
        pool_size: int | None = Field(None, ge=1, le=80)

    class AdvisoryRunBody(BaseModel):  # type: ignore[misc]
        seed: str = Field(..., min_length=1, max_length=4000)
        context: str = Field("", max_length=2000)
        count: int = Field(8, ge=1, le=20)
        strictness: str = Field("medium", pattern="^(low|medium|high)$")
        source: str = Field("deterministic", pattern="^(deterministic|inputer)$")
        pool_size: int | None = Field(None, ge=1, le=80)

    class AdvisoryCandidateBody(BaseModel):  # type: ignore[misc]
        candidate_id: str = Field(..., min_length=1, max_length=120)
        claim: str = Field(..., min_length=1, max_length=4000)
        argument: str = Field(..., min_length=1, max_length=8000)
        context: str = Field("", max_length=2000)
        strictness: str = Field("medium", pattern="^(low|medium|high)$")
        template: str = Field("caller_provided", min_length=1, max_length=120)
        mutation_notes: str = Field("", max_length=1000)

    class AdvisorySelectBody(BaseModel):  # type: ignore[misc]
        seed: str = Field("", max_length=4000)
        candidates: list[AdvisoryCandidateBody] = Field(
            ..., min_length=1, max_length=20
        )

    class NyahlothepOutputBody(BaseModel):  # type: ignore[misc]
        # selected_report comes back from /advisory/run (and friends) as
        # a structured dict. We accept it verbatim and treat every field
        # as data; the LLM never sees it as instructions.
        selected_report: dict[str, Any] = Field(...)
        replication_recipe: dict[str, Any] = Field(...)
        style: str = Field("brief", pattern="^(brief|technical|replication)$")


def create_app(
    store: ReportStore | None = None,
    *,
    advisory_ledger: AdvisoryLedger | None = None,
    llm_client: LLMClient | None = None,
    outputer_cache: LLMResponseCache | None = None,
) -> Any:
    """Build the FastAPI app.

    ``store`` selects the report backend. When omitted, the store is
    resolved from the ``EBF_REPORT_STORE`` env var via :func:`get_store`.
    Tests pass an explicit store to avoid env coupling.

    ``llm_client`` and ``outputer_cache`` let tests inject a deterministic
    fake client and a fresh cache without touching ``EBF_LLM_PROVIDER``
    or the module-level default cache. When both are omitted, the
    Nyahlothep outputer endpoint resolves them lazily per-request.
    """
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "FastAPI not installed. Run: pip install fastapi uvicorn pydantic"
        ) from e
    globals()["Request"] = Request

    if not _HAS_PYDANTIC:  # pragma: no cover
        raise RuntimeError("pydantic not installed. Run: pip install pydantic")

    access_config = load_access_config()
    app = FastAPI(
        title="Effective Boolean Argument Filter",
        version="1.0.0",
        description=(
            "A traceable argument-effect filter. Not a truth oracle. "
            "Inputs are treated as data, never as instructions."
        ),
        docs_url="/docs" if access_config.docs_enabled else None,
        redoc_url="/redoc" if access_config.docs_enabled else None,
        openapi_url="/openapi.json" if access_config.docs_enabled else None,
    )

    reports: ReportStore = store if store is not None else get_store()
    app.state.report_store = reports
    app.state.access_config = access_config
    rate_limiter = FixedWindowRateLimiter(access_config.plan_limits)
    app.state.rate_limiter = rate_limiter
    ledger: AdvisoryLedger = (
        advisory_ledger if advisory_ledger is not None else get_advisory_ledger()
    )
    app.state.advisory_ledger = ledger

    @app.middleware("http")
    async def add_security_headers(request: Any, call_next: Any) -> Any:
        # ebf_identity is read by handlers (e.g. /commercial/status); set a
        # default before any short-circuit so it is always present.
        request.state.ebf_identity = None
        auth = None

        over_limit = content_length_over_limit(request, access_config.max_body_bytes)
        if over_limit is not None:
            # Reject before auth/rate-limit/Pydantic so an oversized payload
            # is never buffered into the engine.
            response = JSONResponse(
                {
                    "detail": (
                        f"request body too large: {over_limit} bytes exceeds the "
                        f"{access_config.max_body_bytes}-byte limit"
                    )
                },
                status_code=413,
            )
        else:
            auth = authenticate_request(request, access_config)
            request.state.ebf_identity = auth.identity

            if access_config.require_api_key and auth.identity is None and not is_public_path(request.url.path):
                response = JSONResponse(
                    {"detail": "API key required"},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="effective-boolean-filter"'},
                )
            else:
                decision = None
                if access_config.rate_limit_enabled and not is_public_path(request.url.path):
                    key, plan = identity_key(request, auth.identity)
                    decision = rate_limiter.check(key, plan)
                    if not decision.allowed:
                        response = JSONResponse(
                            {"detail": "rate limit exceeded"},
                            status_code=429,
                            headers=decision.headers(),
                        )
                    else:
                        response = await call_next(request)
                        response.headers.update(decision.headers())
                else:
                    response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        if auth is not None and auth.identity is not None:
            response.headers["X-EBF-Key-Id"] = auth.identity.key_id
            response.headers["X-EBF-Plan"] = auth.identity.plan
        if auth is not None and auth.bootstrap_token and response.status_code < 400:
            response.set_cookie(
                access_config.cookie_name,
                auth.bootstrap_token,
                max_age=7 * 24 * 60 * 60,
                httponly=True,
                secure=access_config.cookie_secure,
                samesite="lax",
            )
        return response

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        nonce = secrets.token_urlsafe(16)
        response = HTMLResponse(render_dashboard_html(nonce))
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; "
            f"style-src 'nonce-{nonce}'; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/commercial/plans")
    def commercial_plans() -> dict[str, object]:
        return plans_payload()

    @app.get("/commercial/status")
    def commercial_status(request: Request) -> dict[str, object]:
        identity = getattr(request.state, "ebf_identity", None)
        if identity is None:
            return {"authenticated": False, "plan": "anonymous"}
        return {
            "authenticated": True,
            "key_id": identity.key_id,
            "plan": identity.plan,
            "fingerprint": identity.fingerprint,
        }

    @app.get("/legal/terms", response_class=PlainTextResponse)
    def legal_terms() -> PlainTextResponse:
        return PlainTextResponse(TERMS_SUMMARY)

    @app.get("/legal/privacy", response_class=PlainTextResponse)
    def legal_privacy() -> PlainTextResponse:
        return PlainTextResponse(PRIVACY_SUMMARY)


    @app.post("/evaluate_argument")
    def evaluate(body: EvaluateBody) -> dict[str, Any]:
        report = evaluate_argument(
            claim=body.claim,
            argument=body.argument,
            context=body.context,
            task=body.task,
            strictness=body.strictness,  # type: ignore[arg-type]
        )
        out = to_json_dict(report)
        reports.put(report.id, out)
        return out

    @app.post("/generate_probes")
    def probes(body: ProbeBody) -> dict[str, Any]:
        claim_node = parse_claim(body.claim)
        parsed = parse_argument(body.argument)
        conclusion = parsed.conclusion or claim_node
        ps = gen_probes(body.claim, parsed.premises, conclusion, issues=[])
        return {"probes": [p.__dict__ for p in ps]}

    @app.post("/score_probe_results")
    def score_probes(body: ScoreProbesBody) -> dict[str, Any]:
        report = evaluate_argument(
            claim=body.claim,
            argument=body.argument,
            context=body.context,
            strictness=body.strictness,  # type: ignore[arg-type]
        )
        answer_map = {a.question.strip().lower(): a for a in body.answers}
        for p in report.probes:
            a = answer_map.get(p.question.strip().lower())
            if a is None:
                continue
            p.answer = a.answer
            p.passed = a.passed
        sv, eff, bog = score_argument(
            [c for c in report.claims if c.is_premise and not c.is_conclusion],
            next((c for c in report.claims if c.is_conclusion), None),
            report.issues,
            report.contradiction,
            list(report.probes),
            body.strictness,  # type: ignore[arg-type]
        )
        report.score_vector = sv
        report.effectiveness_score = eff
        report.bogusness_score = bog
        out = to_json_dict(report)
        reports.put(report.id, out)
        return out

    @app.post("/advisory/azatoth")
    def advisory_azatoth(body: AdvisoryGenerateBody) -> dict[str, Any]:
        candidates = azatoth_generate(
            body.seed,
            context=body.context,
            count=body.count,
            strictness=body.strictness,  # type: ignore[arg-type]
        )
        return {
            "mode": "contract_v0",
            "azatoth_candidates": [
                advisory_candidate_to_dict(candidate) for candidate in candidates
            ],
        }

    @app.post("/advisory/azatoth/input")
    def advisory_azatoth_input(body: AzatothInputBody) -> dict[str, Any]:
        try:
            result = generate_inputer(
                seed=body.seed,
                context=body.context,
                count=body.count,
                strictness=body.strictness,
                pool_size=body.pool_size,
                client=llm_client,
                cache=outputer_cache,
            )
        except DisabledLLMClientError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except LLMProviderUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except LLMTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc))
        except InputerValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return inputer_result_to_dict(result)

    @app.post("/advisory/nyahlothep")
    def advisory_nyahlothep(body: AdvisorySelectBody) -> dict[str, Any]:
        candidates = [
            AdvisoryCandidate(
                candidate_id=c.candidate_id,
                claim=c.claim,
                argument=c.argument,
                context=c.context,
                strictness=c.strictness,  # type: ignore[arg-type]
                template=c.template,
                mutation_notes=c.mutation_notes,
            )
            for c in body.candidates
        ]
        try:
            run = run_nyahlothep_on_candidates(seed=body.seed, candidates=candidates)
        except PipelineInvariantError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        out = advisory_run_to_dict(run)
        reports.put(run.selected_report.id, out["selected_report"])
        return _attach_advisory_ledger(
            endpoint="/advisory/nyahlothep",
            request_body=body,
            response_body=out,
        )

    @app.post("/advisory/run")
    def advisory_run(body: AdvisoryRunBody) -> dict[str, Any]:
        if body.source == "deterministic":
            try:
                run = run_advisory_wrapper(
                    body.seed,
                    context=body.context,
                    count=body.count,
                    strictness=body.strictness,  # type: ignore[arg-type]
                )
            except PipelineInvariantError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            out = advisory_run_to_dict(run)
            out["azatoth_source"] = "deterministic"
            reports.put(run.selected_report.id, out["selected_report"])
            return _attach_advisory_ledger(
                endpoint="/advisory/run",
                request_body=body,
                response_body=out,
            )

        # body.source == "inputer"
        try:
            inputer_result = generate_inputer(
                seed=body.seed,
                context=body.context,
                count=body.count,
                strictness=body.strictness,
                pool_size=body.pool_size,
                client=llm_client,
                cache=outputer_cache,
            )
        except DisabledLLMClientError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except LLMProviderUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except LLMTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc))
        except InputerValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        try:
            run = run_nyahlothep_on_candidates(
                seed=body.seed,
                candidates=inputer_result.azatoth_candidates,
            )
        except PipelineInvariantError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        out = advisory_run_to_dict(run)
        out["azatoth_source"] = "inputer"
        out["azatoth_inputer"] = {
            "mode": inputer_result.mode,
            "provider": inputer_result.provider,
            "model": inputer_result.model,
            "cache_key": inputer_result.cache_key,
            "cached": inputer_result.cached,
            "pool_size": inputer_result.pool_size,
            "valid_count": inputer_result.valid_count,
            "deduped_count": inputer_result.deduped_count,
        }
        reports.put(run.selected_report.id, out["selected_report"])
        return _attach_advisory_ledger(
            endpoint="/advisory/run",
            request_body=body,
            response_body=out,
        )

    @app.get("/advisory/ledger")
    def advisory_ledger_entries() -> dict[str, Any]:
        try:
            return {"enabled": True, "entries": ledger.list_summaries()}
        except LedgerDisabledError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except LedgerCorruptionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.get("/advisory/ledger/{entry_id}")
    def advisory_ledger_entry(entry_id: str) -> dict[str, Any]:
        try:
            return ledger.get(entry_id)
        except LedgerDisabledError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except LedgerValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LedgerEntryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except LedgerCorruptionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.post("/advisory/ledger/{entry_id}/replay")
    def advisory_ledger_replay(entry_id: str) -> dict[str, Any]:
        try:
            return ledger.replay(entry_id)
        except LedgerDisabledError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except LedgerValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LedgerEntryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except LedgerCorruptionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.post("/advisory/nyahlothep/output")
    def advisory_nyahlothep_output(body: NyahlothepOutputBody) -> dict[str, Any]:
        try:
            result = generate_outputer(
                selected_report=body.selected_report,
                replication_recipe=body.replication_recipe,
                style=body.style,  # type: ignore[arg-type]
                client=llm_client,
                cache=outputer_cache,
            )
        except DisabledLLMClientError as exc:
            # provider configured but not shipping in this build
            raise HTTPException(status_code=503, detail=str(exc))
        except LLMProviderUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except LLMTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc))
        except OutputerValidationError as exc:
            # invalid JSON / schema mismatch / source_report_id mismatch
            raise HTTPException(status_code=422, detail=str(exc))
        return outputer_result_to_dict(result)

    @app.get("/advisory/provider/status")
    def advisory_provider_status() -> dict[str, Any]:
        return provider_status()

    @app.get("/reports/{report_id}")
    def get_report(report_id: str) -> dict[str, Any]:
        try:
            stored = reports.get(report_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid report id")
        if stored is None:
            raise HTTPException(status_code=404, detail="report not found")
        return stored

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def _attach_advisory_ledger(
        *,
        endpoint: str,
        request_body: Any,
        response_body: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = dict(response_body)
        snapshot.pop("ledger", None)
        try:
            response_body["ledger"] = ledger.append(
                run_id=str(snapshot.get("id", "")),
                endpoint=endpoint,
                payload={
                    "request": _model_to_plain_dict(request_body),
                    "response": snapshot,
                },
            )
        except LedgerCorruptionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except LedgerError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return response_body

    return app


def _model_to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()  # type: ignore[no-any-return,attr-defined]
    if hasattr(value, "dict"):
        return value.dict()  # type: ignore[no-any-return,attr-defined]
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"cannot serialize request body: {type(value)!r}")


try:  # pragma: no cover
    app = create_app()
except RuntimeError:  # pragma: no cover
    app = None
