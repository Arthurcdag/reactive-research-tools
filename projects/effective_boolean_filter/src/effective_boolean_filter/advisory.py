"""Deterministic advisory wrapper for the Effective Boolean Filter.

Azatoth generates a bounded swarm of candidate statements. The existing
deterministic filter evaluates each candidate. Nyahlothep then selects the
best candidate using report quality only; it never changes the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Sequence

from .engine import evaluate_argument
from .report import to_json_dict
from .schemas import EvaluationReport, Strictness


MODE = "contract_v0"
CORE_SCORE_FIELDS = (
    "negation_consistency",
    "scope_preservation",
    "definition_stability",
    "contradiction_containment",
)
BAD_POLARITIES = {"untracked_shift", "contradiction"}


@dataclass(frozen=True)
class AdvisoryCandidate:
    candidate_id: str
    claim: str
    argument: str
    context: str
    strictness: Strictness
    template: str
    mutation_notes: str


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: AdvisoryCandidate
    report: EvaluationReport
    ordinal: int


@dataclass(frozen=True)
class NyahlothepSelection:
    selected_candidate_id: str
    rank_reason: str
    ranking: list[dict[str, Any]]


@dataclass(frozen=True)
class AdvisoryRun:
    id: str
    mode: str
    azatoth_candidates: list[AdvisoryCandidate]
    nyahlothep_selection: NyahlothepSelection
    selected_report: EvaluationReport
    replication_recipe: dict[str, Any]


def azatoth_generate(
    seed: str,
    *,
    context: str = "",
    count: int = 8,
    strictness: Strictness = "medium",
) -> list[AdvisoryCandidate]:
    """Generate deterministic candidate statements from a seed statement."""
    if count < 1 or count > 20:
        raise ValueError("count must be between 1 and 20")
    base = _clean_seed(seed)
    templates = _candidate_templates(base)
    candidates: list[AdvisoryCandidate] = []
    for idx in range(count):
        template = templates[idx % len(templates)]
        cycle = idx // len(templates)
        note = template["mutation_notes"]
        if cycle:
            note = f"{note}; deterministic repeat cycle {cycle + 1}"
        candidates.append(
            AdvisoryCandidate(
                candidate_id=f"cand_{idx + 1:03d}_{template['template']}",
                claim=template["claim"],
                argument=template["argument"],
                context=context,
                strictness=strictness,
                template=template["template"],
                mutation_notes=note,
            )
        )
    return candidates


def nyahlothep_select(
    evaluated_candidates: Sequence[CandidateEvaluation],
) -> NyahlothepSelection:
    """Select the strongest evaluated candidate by deterministic report rank."""
    if not evaluated_candidates:
        raise ValueError("at least one evaluated candidate is required")
    ranked = sorted(
        evaluated_candidates,
        key=lambda ev: _rank_tuple(ev),
        reverse=True,
    )
    ranking: list[dict[str, Any]] = []
    for position, ev in enumerate(ranked, 1):
        ranking.append(_summary_for(ev, position))
    selected = ranked[0]
    reason = _rank_reason(selected)
    return NyahlothepSelection(
        selected_candidate_id=selected.candidate.candidate_id,
        rank_reason=reason,
        ranking=ranking,
    )


def run_advisory_wrapper(
    seed: str,
    *,
    context: str = "",
    count: int = 8,
    strictness: Strictness = "medium",
) -> AdvisoryRun:
    candidates = azatoth_generate(
        seed,
        context=context,
        count=count,
        strictness=strictness,
    )
    return run_nyahlothep_on_candidates(seed=seed, candidates=candidates)


def run_nyahlothep_on_candidates(
    *,
    seed: str = "",
    candidates: Sequence[AdvisoryCandidate],
) -> AdvisoryRun:
    """Evaluate caller-provided candidates and select the strongest one."""
    evaluated = _evaluate_candidates(candidates)
    selection = nyahlothep_select(evaluated)
    selected_eval = next(
        ev for ev in evaluated
        if ev.candidate.candidate_id == selection.selected_candidate_id
    )
    recipe = _replication_recipe(seed, selected_eval.candidate, selection.rank_reason)
    return AdvisoryRun(
        id=_run_id(seed, candidates),
        mode=MODE,
        azatoth_candidates=list(candidates),
        nyahlothep_selection=selection,
        selected_report=selected_eval.report,
        replication_recipe=recipe,
    )


def advisory_candidate_to_dict(candidate: AdvisoryCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "claim": candidate.claim,
        "argument": candidate.argument,
        "context": candidate.context,
        "strictness": candidate.strictness,
        "template": candidate.template,
        "mutation_notes": candidate.mutation_notes,
    }


def advisory_run_to_dict(run: AdvisoryRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "mode": run.mode,
        "azatoth_candidates": [
            advisory_candidate_to_dict(c) for c in run.azatoth_candidates
        ],
        "nyahlothep_selection": {
            "selected_candidate_id": run.nyahlothep_selection.selected_candidate_id,
            "rank_reason": run.nyahlothep_selection.rank_reason,
            "ranking": run.nyahlothep_selection.ranking,
        },
        "selected_report": to_json_dict(run.selected_report),
        "replication_recipe": run.replication_recipe,
    }


def _evaluate_candidates(
    candidates: Sequence[AdvisoryCandidate],
) -> list[CandidateEvaluation]:
    evaluated: list[CandidateEvaluation] = []
    for idx, candidate in enumerate(candidates):
        report = evaluate_argument(
            claim=candidate.claim,
            argument=candidate.argument,
            context=candidate.context,
            strictness=candidate.strictness,
            task="advisory wrapper candidate evaluation",
        )
        evaluated.append(
            CandidateEvaluation(candidate=candidate, report=report, ordinal=idx)
        )
    return evaluated


def _rank_tuple(ev: CandidateEvaluation) -> tuple[float, ...]:
    report = ev.report
    rec_rank = {
        "accept": 2,
        "accept_with_caveats": 1,
    }.get(report.recommendation, 0)
    error_count = sum(1 for issue in report.issues if issue.severity == "error")
    structurally_clean = int(
        report.effective_polarity not in BAD_POLARITIES
        and error_count == 0
    )
    core_sum = sum(getattr(report.score_vector, field) for field in CORE_SCORE_FIELDS)
    return (
        rec_rank,
        report.effectiveness_score,
        structurally_clean,
        core_sum,
        -len(report.issues),
        -len(ev.candidate.argument),
        -ev.ordinal,
    )


def _summary_for(ev: CandidateEvaluation, rank: int) -> dict[str, Any]:
    report = ev.report
    error_count = sum(1 for issue in report.issues if issue.severity == "error")
    return {
        "rank": rank,
        "candidate_id": ev.candidate.candidate_id,
        "template": ev.candidate.template,
        "effective_polarity": report.effective_polarity,
        "recommendation": report.recommendation,
        "effectiveness_score": report.effectiveness_score,
        "bogusness_score": report.bogusness_score,
        "issue_count": len(report.issues),
        "error_count": error_count,
        "rank_reason": _rank_reason(ev),
    }


def _rank_reason(ev: CandidateEvaluation) -> str:
    report = ev.report
    errors = [issue.code for issue in report.issues if issue.severity == "error"]
    if errors:
        return (
            f"{ev.candidate.template}: {report.recommendation} with "
            f"{report.effectiveness_score:.3f} effectiveness; errors: "
            f"{', '.join(errors)}"
        )
    return (
        f"{ev.candidate.template}: {report.recommendation} with "
        f"{report.effectiveness_score:.3f} effectiveness and no error issues"
    )


def _replication_recipe(
    seed: str,
    candidate: AdvisoryCandidate,
    rank_reason: str,
) -> dict[str, Any]:
    return {
        "seed": _clean_seed(seed) if seed else "",
        "selected_candidate": advisory_candidate_to_dict(candidate),
        "template": candidate.template,
        "strictness": candidate.strictness,
        "rank_reason": rank_reason,
    }


def _run_id(seed: str, candidates: Sequence[AdvisoryCandidate]) -> str:
    h = hashlib.sha256()
    h.update(_clean_seed(seed).encode("utf-8"))
    for candidate in candidates:
        h.update(candidate.candidate_id.encode("utf-8"))
        h.update(candidate.claim.encode("utf-8"))
        h.update(candidate.argument.encode("utf-8"))
        h.update(candidate.context.encode("utf-8"))
        h.update(candidate.strictness.encode("utf-8"))
    return f"adv_{h.hexdigest()[:10]}"


def _clean_seed(seed: str) -> str:
    cleaned = " ".join(seed.strip().split())
    return cleaned.rstrip(" .") or "P"


def _candidate_templates(base: str) -> list[dict[str, str]]:
    return [
        {
            "template": "clean_double_negation",
            "claim": base,
            "argument": f"It is not the case that not {base}. Therefore {base}.",
            "mutation_notes": "Tracks logical double negation over the same object.",
        },
        {
            "template": "epistemic_absence",
            "claim": base,
            "argument": f"There is no evidence against {base}. Therefore {base}.",
            "mutation_notes": "Tests whether absence of disproof is mistaken for proof.",
        },
        {
            "template": "simulation_scope_shift",
            "claim": f"{base} works in production",
            "argument": f"{base} works in simulation. Therefore {base} works in production.",
            "mutation_notes": "Forces the filter to detect simulation-to-production drift.",
        },
        {
            "template": "legal_to_physical_shift",
            "claim": f"{base} is physically possible",
            "argument": f"{base} is not legally impossible. Therefore {base} is physically possible.",
            "mutation_notes": "Tests legal permission against physical possibility.",
        },
        {
            "template": "possibility_to_actuality",
            "claim": f"{base} is true",
            "argument": f"{base} is possible in theory. Therefore {base} is true.",
            "mutation_notes": "Tests whether possibility is promoted into actuality.",
        },
        {
            "template": "fallacy_fallacy",
            "claim": f"{base} is false",
            "argument": f"The argument for {base} is a weak argument. Therefore {base} is false.",
            "mutation_notes": "Tests whether weak support is confused with falsity.",
        },
        {
            "template": "sample_to_scale",
            "claim": f"{base} scales to a million users",
            "argument": f"{base} passed a small sample. Therefore {base} scales to a million users.",
            "mutation_notes": "Tests whether a small sample is overgeneralized.",
        },
        {
            "template": "non_implication",
            "claim": f"{base} follows",
            "argument": f"{base} does not imply deployment readiness. Therefore deployment readiness follows.",
            "mutation_notes": "Tests explicit non-implication against a follows-claim.",
        },
    ]
