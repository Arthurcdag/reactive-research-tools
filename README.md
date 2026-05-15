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
├── GITHUB_SETUP.md
├── requirements.txt
└── README.md
```

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
GET  /commercial/plans
GET  /commercial/status
POST /commercial/webhook/stripe
GET  /legal/terms
GET  /legal/privacy
```

Enable the Stripe webhook with:

```bash
EBF_STRIPE_WEBHOOK_SECRET=whsec_... \
EBF_CUSTOMER_REGISTRY=/data/customer_registry.json \
EBF_PAYMENT_WEBHOOK_LEDGER=/data/payment_webhook_ledger.jsonl
```

The endpoint verifies the `Stripe-Signature` header, dedupes by event id
via the ledger, and updates the customer registry in place. Without those
env vars it returns `503`.

For deployments past a handful of customers, opt into the SQLite tenant
database:

```bash
EBF_TENANT_DB=tenant:/data/tenant.sqlite
```

That gives you DB-backed API keys (fast SHA-256 lookup, complementary to
the env-var `EBF_API_KEYS` list) and report storage with optional
per-row expiry. The payment webhook mirrors every applied event into the
DB's `tenants` table so plan/status changes from Stripe are queryable
without re-reading the JSON registry. Admin via
`scripts/tenant_db_admin.py` — list tenants, mint keys (token shown
once), revoke keys, reap expired reports.

See [`docs/OPERATIONS_AND_MONETIZATION.md`](docs/OPERATIONS_AND_MONETIZATION.md)
for the second-company separation rule, pricing tiers, Stripe event
mapping, tenant-DB migration sketch, and the remaining legal items.

Run the Xi–Jensen dashboard if the corresponding generated scripts and dependencies are present:

```bash
python projects/xi_jensen_pipeline/scripts/xi_jensen_frontier_dashboard.py --help
```

## Status

This repo is an initial research/workbench packaging. It contains:
- working MVP code for the argument filter,
- generated developer briefs,
- Xi–Jensen scripts developed during the research session,
- workflow notes,
- issue templates for implementation.

No final scientific claims should be treated as certified unless they pass the stated certification pipeline.
