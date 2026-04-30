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

LLM is **not** in the deterministic path. The current MVP is rule-based. An LLM wrapper for advisory parsing/probe paraphrasing can be added later, behind structured-JSON validation.

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
| GET    | /reports/{id}         | Fetch a stored report             |
| GET    | /health               | Liveness                          |

Inputs are treated as **data**, never as instructions to the system.
The browser dashboard uses text-only rendering for evaluated content and is
served with a restrictive content security policy.

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
| 4. API + CLI                   | ✅ FastAPI (4 endpoints), CLI (json/human/both) |
| 5. Benchmarks                  | ✅ 55 labelled examples + regression CI |
| LLM advisory wrapper            | ⏳ deferred — deterministic core comes first per spec |
