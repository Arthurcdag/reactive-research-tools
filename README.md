# Reactive Research Tools

This repository packages the work developed so far into two connected research/tooling tracks.

## 1. Effective Boolean Argument Filter

A traceable argument-effect filter. It is not a truth oracle. It checks whether an argument preserves its yes/no structure under negation, scope, context, contradiction containment, and reactive probes.

Core rule:

> No untracked polarity shifts.

The MVP distinguishes:

```text
not not P -> effective_yes
```

from:

```text
no evidence against P -> unknown, not effective_yes
```

because the second form is epistemic absence-of-disproof, not ontological double negation.

Location:

```text
projects/effective_boolean_filter
```

## 2. Xi–Jensen Certification Pipeline

A numerical/research workflow for fast exploratory scans plus progressively stronger certification.

The workflow evolved into:

```text
fast dashboard scan
-> verification/triage
-> scaled deepcheck
-> certified merge
-> certification batch
-> certified merge v2
-> certification status
-> repeat
```

The key lesson was that fast/numpy roots are useful as a candidate generator, while scaled high-precision deepcheck is the trusted certification layer.

Location:

```text
projects/xi_jensen_pipeline
```

## Repository layout

```text
.
├── docs/
│   ├── developer_briefs/
│   └── source_notes/
├── projects/
│   ├── effective_boolean_filter/
│   └── xi_jensen_pipeline/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── CHANGELOG.md
├── GITHUB_SETUP.md
├── requirements.txt
└── README.md
```

Shipped history lives in [`CHANGELOG.md`](CHANGELOG.md); forward-looking work
lives in [`docs/DEVELOPER_NEXT_STEPS.md`](docs/DEVELOPER_NEXT_STEPS.md).

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

Run the Effective Boolean Filter MVP:

```bash
python projects/effective_boolean_filter/cli.py \
  --claim "This method proves X" \
  --argument "There is no evidence against X, therefore X is true" \
  --context "scientific argument"
```

Run the Effective Boolean Filter API and dashboard:

```bash
python -m uvicorn effective_boolean_filter.api:app \
  --app-dir projects/effective_boolean_filter/src \
  --reload
```

Then open:

```text
http://127.0.0.1:8000/
```

The dashboard is served with a restrictive content security policy and
localhost binding by default. Keep that binding unless you intentionally
want to expose the API on a network.

Optional advisory ledger:

```bash
EBF_ADVISORY_LEDGER=file:./local/advisory-ledger.jsonl \
  python -m uvicorn effective_boolean_filter.api:app \
    --app-dir projects/effective_boolean_filter/src \
    --host 127.0.0.1 \
    --port 8000
```

When enabled, `/advisory/run` and `/advisory/nyahlothep` append full local
advisory snapshots to JSONL. `/advisory/ledger/{entry_id}/replay` verifies the
hash chain and reruns deterministic selection from the stored candidates.

Optional live LLM provider for Azatoth/Nyahlothep advisory prose/candidate
generation:

```bash
EBF_LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=... \
EBF_LLM_MODEL=claude-sonnet-4-5 \
  python -m uvicorn effective_boolean_filter.api:app \
    --app-dir projects/effective_boolean_filter/src \
    --host 127.0.0.1 \
    --port 8000
```

The provider is advisory only. Its JSON is still validated before use, and the
deterministic filter remains the only verdict source.
The dashboard also exposes a no-network provider status check so config can be
verified without sending seed/report data to a provider.

## Production / commercial mode

For a public or paid deployment, enable API-key gating and persistent report
storage:

```bash
EBF_PUBLIC_MODE=1 \
EBF_API_KEYS=customer-a:starter:<long-random-secret> \
EBF_REPORT_STORE=file:/data/reports \
python -m uvicorn effective_boolean_filter.api:app \
  --app-dir projects/effective_boolean_filter/src \
  --host 0.0.0.0 \
  --port 8000
```

Then open the dashboard once with:

```text
https://your-domain/?access_key=<long-random-secret>
```

Commercial endpoints:

```text
GET /commercial/plans
GET /commercial/status
GET /legal/terms
GET /legal/privacy
```

See [`docs/OPERATIONS_AND_MONETIZATION.md`](docs/OPERATIONS_AND_MONETIZATION.md)
for the second-company separation rule, pricing tiers, deployment process, and
remaining legal/payment work.

Run the Xi–Jensen dashboard if the corresponding generated scripts and dependencies are present:

```bash
python projects/xi_jensen_pipeline/scripts/xi_jensen_frontier_dashboard.py --help
```

## Public surface

This is the contract callers can depend on. Endpoints not in this table are
internal and may change or disappear without notice. "Stable" means the
request/response shape will not break without a `CHANGELOG.md` entry.

### Effective Boolean Filter API (`effective_boolean_filter.api:app`)

| Method & path | Stability | Auth in public mode | Purpose |
| --- | --- | --- | --- |
| `GET /` | stable | required | Browser dashboard (HTML, restrictive CSP) |
| `GET /health` | stable | public (no key) | Liveness probe |
| `POST /evaluate_argument` | stable | required | Run the deterministic filter on one claim/argument |
| `POST /generate_probes` | stable | required | Generate reactive probes (parse-only, cheap) |
| `POST /score_probe_results` | stable | required | Re-score a report with probe answers |
| `GET /reports/{id}` | stable | required | Fetch a stored report by id |
| `POST /advisory/run` | stable | required | Orchestrated wrapper: Azatoth → filter → Nyahlothep |
| `POST /advisory/azatoth` | stable | required | Deterministic candidate generation only |
| `POST /advisory/azatoth/input` | stable | required | LLM-backed candidate generation (inputer) |
| `POST /advisory/nyahlothep` | stable | required | Select from caller-supplied candidates |
| `POST /advisory/nyahlothep/output` | stable | required | LLM narration of a selected report (outputer) |
| `GET /advisory/provider/status` | stable | required | No-network provider config check |
| `GET /advisory/ledger` | stable | required | List advisory ledger entries (when enabled) |
| `GET /advisory/ledger/{entry_id}` | stable | required | Fetch one ledger entry |
| `POST /advisory/ledger/{entry_id}/replay` | stable | required | Verify the hash chain and re-run selection |
| `GET /commercial/plans` | stable | public (no key) | Plan/pricing metadata |
| `GET /commercial/status` | stable | required | Caller's authenticated plan/identity |
| `GET /legal/terms` | stable | public (no key) | Draft terms of service (plain text) |
| `GET /legal/privacy` | stable | public (no key) | Draft privacy notice (plain text) |
| `GET /docs`, `/redoc`, `/openapi.json` | internal | off in public mode | FastAPI's generated docs; default-on locally only |

Notes:

- **Most-used path:** `POST /advisory/run` already chains the inputer, the
  deterministic filter, and the Nyahlothep selector. Prefer it over wiring
  `/advisory/azatoth/input` + `/advisory/nyahlothep` by hand unless you need
  the intermediate candidate list.
- **Verdict source:** only the deterministic engine produces a verdict. The
  `/advisory/*` LLM endpoints are advisory and pass through structured-JSON
  validation before any output is surfaced.
- **Public mode** (`EBF_PUBLIC_MODE=1`) gates every non-public row above
  behind an API key and applies per-plan rate limits. The "public (no key)"
  rows stay reachable so health checks and plan/legal metadata work for
  anonymous callers. See [Production / commercial mode](#production--commercial-mode).
- **Errors are visible:** typed failures map to distinct HTTP statuses
  (`401`, `413`, `422`, `429`, `502`, `503`, `504`) — there is no silent
  fallback.

### Xi–Jensen pipeline

The Xi–Jensen scripts under `projects/xi_jensen_pipeline/scripts/` are a CLI
research toolchain, not a network service. Each script's `--help` is its
interface; see `projects/xi_jensen_pipeline/docs/` for per-script notes.

## Status

This repo is an initial research/workbench packaging. It contains:
- working MVP code for the argument filter,
- generated developer briefs,
- Xi–Jensen scripts developed during the research session,
- workflow notes,
- issue templates for implementation.

No final scientific claims should be treated as certified unless they pass the stated certification pipeline.
