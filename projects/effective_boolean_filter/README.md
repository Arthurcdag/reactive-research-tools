# Effective Boolean Argument Filter

A traceable filter for arguments and claims. **Not a truth oracle.** It checks whether an argument preserves its yes/no structure under negation, scope, definition, context, contradiction containment, and reactive probes.

## Core principle

```text
No untracked polarity shifts.
```

A claim only earns a yes/no verdict when the transformations that produce that verdict are tracked across the same object, scope, definition, context, and negation type.

```text
not not P                 -> effective_yes
no evidence against P     -> unknown / untracked_shift
not legally impossible    -> untracked_shift if conclusion is "physically possible"
works in simulation       -> untracked_shift if conclusion is "works in production"
                             (unless a bridge premise like "validated against
                             production traces" is present)
```

## Architecture

LLM is **not** in the deterministic path. The core MVP is rule-based.
The advisory wrapper V0 is contract-first and deterministic: Azatoth makes
candidate statements, the filter evaluates each one, and Nyahlothep selects
the strongest candidate from filter reports only. A live Anthropic provider
can be enabled for the inputer/outputer wrapper behind the same structured
contract; provider output never becomes a verdict directly.

```text
raw argument
  -> parser            (controlled phrase set; advisory)
  -> polarity engine   (negation parity + invariants; authoritative)
  -> scope tracker     (legal/sim/prod/modal bridges; authoritative)
  -> definition tracker (versioned definition_id)
  -> contradiction module (containment, no explosion)
  -> probe generator   (typed reactive probes; advisory)
  -> scoring engine    (ScoreVector with reasons; authoritative)
  -> report layer      (JSON + human-readable)
```

## CLI

```bash
python cli.py \
  --claim "This method proves X" \
  --argument "There is no evidence against X, therefore X is true" \
  --context "scientific argument" \
  --format human    # or json, both
```

Exit code is 0 for `accept` / `accept_with_caveats`, 1 otherwise.

## API

```bash
pip install fastapi uvicorn pydantic
uvicorn effective_boolean_filter.api:app --reload
```

Endpoints (per spec section 11):

| Method | Path                  | Purpose                          |
|--------|-----------------------|----------------------------------|
| GET    | /                     | Browser dashboard                 |
| POST   | /evaluate_argument    | Run the full pipeline             |
| POST   | /generate_probes      | Probes only (no scoring)          |
| POST   | /score_probe_results  | Re-score after answering probes   |
| POST   | /advisory/azatoth     | Generate candidate statements     |
| POST   | /advisory/nyahlothep  | Select from caller candidates     |
| POST   | /advisory/run         | Generate, evaluate, select        |
| GET    | /advisory/provider/status | Check advisory provider config |
| GET    | /advisory/ledger      | List advisory ledger entries      |
| GET    | /advisory/ledger/{id} | Fetch an advisory ledger entry    |
| POST   | /advisory/ledger/{id}/replay | Verify and replay an entry |
| GET    | /reports/{id}         | Fetch a stored report             |
| GET    | /health               | Liveness                          |

Inputs are treated as **data**, never as instructions to the system.
The browser dashboard uses text-only rendering for evaluated content and is
served with a restrictive content security policy.

### Report storage

Evaluation reports are kept in a swappable backend. Configure via the
`EBF_REPORT_STORE` env var:

| Value                | Backend           | Notes                                    |
|----------------------|-------------------|------------------------------------------|
| (unset) / `memory`   | `InMemoryStore`   | Default. Ephemeral; lost on restart.     |
| `file:/path/to/dir`  | `FileStore`       | One JSON file per report; atomic write.  |

Example:

```bash
EBF_REPORT_STORE=file:/var/lib/ebf-reports \
  uvicorn effective_boolean_filter.api:app --host 127.0.0.1 --port 8000
```

`create_app(store=...)` accepts an explicit store instance for tests and
custom backends.

### Advisory wrapper

The wrapper is a deterministic V0 contract. It performs no network calls and
uses no provider keys.

```bash
curl -X POST http://127.0.0.1:8000/advisory/run \
  -H "Content-Type: application/json" \
  -d "{\"seed\":\"X is true\",\"context\":\"science\",\"count\":8}"
```

Response shape:

- `id`
- `mode: "contract_v0"`
- `azatoth_candidates`
- `nyahlothep_selection`
- `selected_report`
- `replication_recipe`
- `trace` with `mode: "pipeline_trace_v0"` and ordered advisory stages
- `gates` with promotion and reality-gate receipts

Only the selected candidate's report is stored in the report store. Other
candidate evaluations are returned as ranking summaries.

Trace/gate metadata is provenance only. It proves that the selected report came
from evaluated filter output; it does not change the deterministic verdict.

### Advisory ledger

The advisory ledger is off by default. Enable it only for local provenance
work:

```bash
EBF_ADVISORY_LEDGER=file:/path/to/advisory-ledger.jsonl \
  uvicorn effective_boolean_filter.api:app --host 127.0.0.1 --port 8000
```

When enabled, `/advisory/run` and `/advisory/nyahlothep` append full JSONL
snapshots after the selected report is stored. Each entry includes a sequence,
previous hash, entry hash, request payload, and advisory response without
ledger metadata. Replay verifies the hash chain, rebuilds candidates from the
stored snapshot, re-runs the deterministic filter/selection path, and reports
any mismatches. It does not call a live provider.

### Live advisory provider

The default provider is still the deterministic fake client. Enable the
Anthropic adapter explicitly:

```bash
EBF_LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=... \
EBF_LLM_MODEL=claude-sonnet-4-5 \
  uvicorn effective_boolean_filter.api:app --host 127.0.0.1 --port 8000
```

Optional provider settings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `EBF_ANTHROPIC_VERSION` | `2023-06-01` | Anthropic API version header |
| `EBF_LLM_BASE_URL` | `https://api.anthropic.com` | Direct API base URL |
| `EBF_LLM_MAX_TOKENS` | `4096` | Non-streaming response token cap |

Provider failures surface visibly as API errors. Provider text is parsed as
JSON and then validated by the existing inputer/outputer schemas before it can
enter the advisory wrapper.

`GET /advisory/provider/status` performs a no-network config check for the
dashboard. It reports provider/model/configured status and whether a credential
is present, but never returns the credential value.

## Output concepts

Polarity values: `effective_yes`, `effective_no`, `unknown`, `unstable`, `untracked_shift`, `contradiction`.

Score vector (8 fields, each 0–1, each with a reason string when penalised):

- `negation_consistency`
- `scope_preservation`
- `definition_stability`
- `context_fit`
- `contradiction_containment`
- `reactive_performance`
- `testability`
- `implementation_relevance`

`effectiveness_score = weighted_sum(...)`, `bogusness_score = 1 - effectiveness_score`. When polarity is `untracked_shift` or `contradiction`, the score is clamped so the structural verdict shows up numerically.

## Tests

```bash
python -m pytest projects/effective_boolean_filter/tests/
```

Covers: negation parity, scope shifts, contradiction containment, probe generation, scoring/report shape, the full FastAPI surface, plus regression on a 50+ example labelled benchmark in [`benchmarks/examples.jsonl`](benchmarks/examples.jsonl).

## Status

| Sprint | Coverage |
|--------|----------|
| 1. Core engine                 | ✅ schemas, parser, polarity engine, parity invariants |
| 2. Scope + contradiction       | ✅ scope tracker, definition tracker, no-explosion contradictions |
| 3. Reactive probes             | ✅ typed probe generator + score wiring |
| 4. API + CLI                   | ✅ FastAPI, advisory endpoints, CLI (json/human/both) |
| 5. Benchmarks                  | ✅ 55 labelled examples + regression CI |
| Advisory wrapper V0             | contract-first Azatoth/Nyahlothep, no live LLM |
