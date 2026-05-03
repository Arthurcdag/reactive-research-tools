"""FastAPI surface for the Effective Boolean Argument Filter (spec Section 11).

Endpoints:
  POST /evaluate_argument
  POST /generate_probes
  POST /score_probe_results
  POST /advisory/azatoth
  POST /advisory/nyahlothep
  POST /advisory/run
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
from .dashboard import render_dashboard_html
from .parser import parse_argument, parse_claim
from .probes import generate_probes as gen_probes
from .report import to_json_dict
from .scoring import score_argument
from .storage import ReportStore, get_store
from .advisory import (
    AdvisoryCandidate,
    advisory_candidate_to_dict,
    advisory_run_to_dict,
    azatoth_generate,
    run_advisory_wrapper,
    run_nyahlothep_on_candidates,
)


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


def create_app(store: ReportStore | None = None) -> Any:
    """Build the FastAPI app.

    ``store`` selects the report backend. When omitted, the store is
    resolved from the ``EBF_REPORT_STORE`` env var via :func:`get_store`.
    Tests pass an explicit store to avoid env coupling.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "FastAPI not installed. Run: pip install fastapi uvicorn pydantic"
        ) from e

    if not _HAS_PYDANTIC:  # pragma: no cover
        raise RuntimeError("pydantic not installed. Run: pip install pydantic")

    app = FastAPI(
        title="Effective Boolean Argument Filter",
        version="1.0.0",
        description=(
            "A traceable argument-effect filter. Not a truth oracle. "
            "Inputs are treated as data, never as instructions."
        ),
    )

    reports: ReportStore = store if store is not None else get_store()
    app.state.report_store = reports

    @app.middleware("http")
    async def add_security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
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
        run = run_nyahlothep_on_candidates(seed=body.seed, candidates=candidates)
        out = advisory_run_to_dict(run)
        reports.put(run.selected_report.id, out["selected_report"])
        return out

    @app.post("/advisory/run")
    def advisory_run(body: AdvisoryGenerateBody) -> dict[str, Any]:
        run = run_advisory_wrapper(
            body.seed,
            context=body.context,
            count=body.count,
            strictness=body.strictness,  # type: ignore[arg-type]
        )
        out = advisory_run_to_dict(run)
        reports.put(run.selected_report.id, out["selected_report"])
        return out

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

    return app


try:  # pragma: no cover
    app = create_app()
except RuntimeError:  # pragma: no cover
    app = None
