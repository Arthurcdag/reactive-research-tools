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
  POST /commercial/webhook/stripe
  GET  /
  GET  /reports/{id}

FastAPI/Pydantic are imported lazily so ``import effective_boolean_filter`` does
not require them; install with ``pip install fastapi uvicorn pydantic`` to
boot the API.
"""
from __future__ import annotations

import json
import os
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
    identity_key,
    is_public_path,
    load_access_config,
)
from .parser import parse_argument, parse_claim
from .payment_webhook import (
    EventApplicationError,
    PaymentWebhookConfig,
    WebhookConfigError,
    WebhookPayloadError,
    WebhookSignatureError,
    apply_payment_event,
    get_ledger,
    load_payment_webhook_config,
)
from .payment_webhook_stripe import parse_stripe_event, verify_stripe_signature
from .probes import generate_probes as gen_probes
from .report import to_json_dict
from .scoring import score_argument
from .storage import ReportStore, TenantReportStore, get_store
from .tenant_db import TenantDatabase, open_tenant_db_from_env
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
    payment_webhook_config: PaymentWebhookConfig | None = None,
    tenant_db: TenantDatabase | None = None,
) -> Any:
    """Build the FastAPI app.

    ``store`` selects the report backend. When omitted, the store is
    resolved from the ``EBF_REPORT_STORE`` env var via :func:`get_store`.
    Tests pass an explicit store to avoid env coupling.

    ``llm_client`` and ``outputer_cache`` let tests inject a deterministic
    fake client and a fresh cache without touching ``EBF_LLM_PROVIDER``
    or the module-level default cache. When both are omitted, the
    Nyahlothep outputer endpoint resolves them lazily per-request.

    ``payment_webhook_config`` selects the payment-webhook configuration.
    When omitted it is loaded from ``EBF_STRIPE_WEBHOOK_SECRET`` /
    ``EBF_CUSTOMER_REGISTRY`` / ``EBF_PAYMENT_WEBHOOK_LEDGER`` env vars.
    The default (unset) keeps the endpoint disabled and returning 503.

    ``tenant_db`` opens the SQLite tenant database. When omitted it is
    loaded from ``EBF_TENANT_DB``. The DB is consulted for:

      * auth — keys not in ``EBF_API_KEYS`` are looked up by SHA-256
        token hash in ``api_keys``;
      * reports — when ``EBF_REPORT_STORE=tenant:...`` or the caller
        passes a :class:`TenantReportStore`, all reports live in the
        ``reports`` table;
      * the payment webhook — every applied event upserts the tenant
        row in the ``tenants`` table in addition to mutating the JSON
        registry (the two stay in sync; either is enough to answer
        "what plan is this tenant on?").

    The default (unset) keeps the env-var keys, file/memory report
    store, and JSON-only webhook path working unchanged.
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

    # Resolve the tenant DB first so the report store can fall back to
    # a tenant-backed one when no explicit store was provided and the
    # env points at a SQLite path.
    resolved_tenant_db: TenantDatabase | None = (
        tenant_db if tenant_db is not None else open_tenant_db_from_env()
    )
    app.state.tenant_db = resolved_tenant_db

    if store is not None:
        reports: ReportStore = store
    else:
        env_spec = (os.environ.get("EBF_REPORT_STORE") or "").strip()
        if env_spec:
            reports = get_store(env_spec)
        elif resolved_tenant_db is not None:
            # Convenience: with a tenant DB but no explicit report store,
            # send reports into that DB so a single SQLite file holds
            # both auth state and persisted reports.
            reports = TenantReportStore(resolved_tenant_db)
        else:
            reports = get_store()
    app.state.report_store = reports
    app.state.access_config = access_config
    rate_limiter = FixedWindowRateLimiter(access_config.plan_limits)
    app.state.rate_limiter = rate_limiter
    ledger: AdvisoryLedger = (
        advisory_ledger if advisory_ledger is not None else get_advisory_ledger()
    )
    app.state.advisory_ledger = ledger

    webhook_config: PaymentWebhookConfig = (
        payment_webhook_config
        if payment_webhook_config is not None
        else load_payment_webhook_config()
    )
    app.state.payment_webhook_config = webhook_config

    @app.middleware("http")
    async def add_security_headers(request: Any, call_next: Any) -> Any:
        auth = authenticate_request(
            request, access_config, tenant_db=resolved_tenant_db
        )
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
        if auth.identity is not None:
            response.headers["X-EBF-Key-Id"] = auth.identity.key_id
            response.headers["X-EBF-Plan"] = auth.identity.plan
        if auth.bootstrap_token and response.status_code < 400:
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

    @app.post("/commercial/webhook/stripe")
    async def commercial_webhook_stripe(request: Request) -> dict[str, Any]:
        """Receive Stripe webhook events and apply them to the customer registry.

        Visible-failure error mapping (no silent swallowing):

        * ``503`` — webhook not configured (missing secret or registry)
        * ``400`` — body is not valid JSON, or Stripe payload is malformed
        * ``401`` — signature missing, expired, or invalid
        * ``500`` — apply step hit a non-recoverable I/O / schema error

        On success (including ``ignored``, ``duplicate``,
        ``rejected_no_customer``) the response is ``200`` so Stripe does
        not retry forever. The ledger entry records the actual outcome.
        """
        if not webhook_config.enabled:
            raise HTTPException(
                status_code=503,
                detail=(
                    "payment webhook not configured; set "
                    "EBF_STRIPE_WEBHOOK_SECRET and EBF_CUSTOMER_REGISTRY to enable"
                ),
            )
        assert webhook_config.stripe_secret is not None
        assert webhook_config.registry_path is not None

        raw_body = await request.body()
        signature_header = request.headers.get("stripe-signature", "")
        try:
            verify_stripe_signature(
                payload=raw_body,
                signature_header=signature_header,
                secret=webhook_config.stripe_secret,
                tolerance_seconds=webhook_config.signature_tolerance_seconds,
            )
        except WebhookSignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc))

        try:
            envelope = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"webhook body is not valid JSON: {exc}"
            )

        try:
            event = parse_stripe_event(envelope)
        except WebhookPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        ledger_handle = get_ledger(webhook_config)
        try:
            application = apply_payment_event(
                event,
                registry_path=webhook_config.registry_path,
                ledger=ledger_handle,
            )
        except EventApplicationError as exc:
            # I/O or schema failure on the registry side: this is a 500
            # because Stripe should retry once we fix it.
            raise HTTPException(status_code=500, detail=str(exc))
        except WebhookConfigError as exc:  # pragma: no cover - guarded above
            raise HTTPException(status_code=503, detail=str(exc))

        # Mirror the registry mutation into the tenant DB when one is
        # configured. The DB is a derived view (the JSON registry stays
        # authoritative for the webhook path) so a transient SQLite
        # error must not fail the webhook: Stripe would retry and the
        # JSON registry already reflects the truth. Operators can rerun
        # ``tenant-db sync-from-registry`` (CLI) to backfill.
        if application.applied and resolved_tenant_db is not None and application.after:
            after = application.after
            try:
                resolved_tenant_db.upsert_tenant(
                    application.customer_id,
                    plan=str(after.get("plan") or "demo"),
                    status=str(after.get("status") or "active"),
                    payment_reference=str(after.get("payment_reference", "")),
                    monthly_amount=str(after.get("monthly_amount", "")),
                    currency=str(after.get("currency", "")),
                )
            except Exception:  # pragma: no cover - mirroring is best-effort
                pass

        return application.to_dict()

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
