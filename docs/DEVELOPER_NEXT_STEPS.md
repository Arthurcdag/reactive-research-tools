# Developer Next Steps

This repo is now on `main` after PR #2. The Effective Boolean Filter MVP has a
CLI, FastAPI surface, browser dashboard, benchmark tests, and passing GitHub
Actions.

## Current Verified State

- `main` includes merge commit `7fb4a6d`.
- Dashboard feature commit: `10fbd1f`.
- CI dependency fix: `093efef`.
- GitHub Actions `Python tests` passes on `main`.
- Local verification command:

```bash
python -m pytest projects/effective_boolean_filter/tests/
```

Expected result: all tests pass.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest projects/effective_boolean_filter/tests/
```

Run the dashboard locally:

```bash
python -m uvicorn effective_boolean_filter.api:app ^
  --app-dir projects/effective_boolean_filter/src ^
  --host 127.0.0.1 ^
  --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Keep the default localhost binding unless the API is protected with auth and
rate limiting.

## Safety Notes

- Treat all evaluated claims and arguments as untrusted input.
- The dashboard must render evaluated content as text, never HTML.
- Keep the restrictive CSP on `GET /`.
- Do not expose the FastAPI app with `--host 0.0.0.0` until these are added:
  authentication, request rate limits, request body limits at the server/proxy
  layer, and deployment logging rules that avoid storing sensitive user inputs.
- The deterministic engine must remain authoritative. Any LLM feature should be
  advisory only and validated through structured JSON before entering reports.

## Immediate Next Tasks

1. ~~Add durable report storage.~~ ✅ Shipped on branch `codex/report-storage`.
   - `storage.py` provides `InMemoryStore` (default) and `FileStore`.
   - Selected via the `EBF_REPORT_STORE` env var: unset/`memory` or
     `file:/path/to/dir`.
   - `create_app(store=...)` lets tests inject a backend explicitly.
   - Round-trip persistence across app recreation is covered in
     `tests/test_api.py::test_file_store_persists_across_app_recreation`.

2. ~~Improve dashboard usability without adding a frontend build step.~~ ✅ Shipped on branch `codex/dashboard-ux`.
   - Replaced the single "Clean case" button with a row of four labelled
     sample-preset buttons (clean double negation, epistemic shift, scope
     shift, contained contradiction). Each writes its claim/argument/
     context/strictness into the form via `addEventListener` (no inline
     handlers, CSP-safe).
   - Added a compact score-vector table that renders all eight fields
     with value, progress bar, and per-field reason strings on every
     evaluation.
   - Added a "Copy JSON" button that uses `navigator.clipboard.writeText`
     gated behind the click handler (so clipboard access only occurs on
     explicit user activation), with a `role="status"` `aria-live="polite"`
     feedback span that shows "Copied to clipboard." or an error message
     and clears after 2.5s. Refuses to copy when no report has been run.
   - Regression tests in `tests/test_api.py` cover the four preset
     buttons, all eight score-vector fields in the rendered HTML, the
     copy-JSON button + feedback element + Clipboard API usage, and the
     no-inline-event-handler invariant.

3. ~~Add API error tests.~~ ✅ Shipped on branch `codex/api-error-tests`.
   - `tests/test_api_validation.py` (52 tests) covers: over-length
     claim/argument/context/task/probe-answer bodies, the strictness
     whitelist (case-sensitive, with wrong-type rejection), malformed
     probe answers (missing fields, wrong types, empty question,
     non-list `answers`), generic missing/non-JSON/wrong-type bodies,
     CSP regression (all 7 directives + per-response nonce + cache),
     extra security headers, middleware coverage on non-dashboard
     endpoints, plus 404/405 surface.

4. ~~Add a public-sharing deployment checklist.~~ ✅ Shipped on branch `codex/deploy-checklist`.
   - See [`docs/PUBLIC_DEPLOYMENT_CHECKLIST.md`](PUBLIC_DEPLOYMENT_CHECKLIST.md).
   - Covers auth, rate limiting, HTTPS, CORS, logging, data retention,
     network exposure, dependency hygiene, engine-integrity carry-over
     from the existing safety notes, pre-launch verification steps,
     and an explicit "what's safe today" section that draws the line
     at local-only / SSH-forwarded use vs. public binding.

5. ~~Address GitHub Actions maintenance.~~ ✅ Shipped on branch `codex/ci-actions-bump`.
   - Bumped `actions/checkout@v4` → `@v6` and `actions/setup-python@v5` → `@v6`.
   - Both v6 releases run on Node 24, so the Node 20 deprecation warning
     no longer fires. Requires GitHub-hosted runner 2.327.1+ (ubuntu-latest
     is kept current automatically).
   - No workflow logic changed; the `pytest` command and Python version
     pin are untouched.

6. ~~Add the Azatoth/Nyahlothep advisory wrapper V0.~~ Shipped on branch
   `codex/advisory-wrapper-v0`.
   - `advisory.py` provides a deterministic contract: Azatoth generates a
     bounded candidate swarm, the filter evaluates each candidate, and
     Nyahlothep selects from filter reports only.
   - Adds `POST /advisory/azatoth`, `POST /advisory/nyahlothep`, and
     `POST /advisory/run`.
   - The dashboard has a compact wrapper panel with candidate ranking,
     selected candidate display, and a "Load selected" action.
   - No provider keys, no network calls, and no live LLM dependency are part
     of this V0.
   - V1 should build the Nyahlothep/outputer path first: output failures are
     visible, and the outputer needs the same API client, prompt caching, and
     JSON validation plumbing that Azatoth/inputer will reuse later.

7. ~~Build Nyahlothep outputer V1.~~ ✅ Shipped on branch
   `codex/nyahlothep-outputer-v1`.
   - `llm_client.py` defines the `LLMClient` interface, ships
     `DeterministicFakeClient` as the default, and reserves the provider
     adapter slot behind `EBF_LLM_PROVIDER`. Selecting any non-fake value
     raises `DisabledLLMClientError` so callers see a visible failure
     rather than a silent stub.
   - `llm_prompts.py` carries the versioned `nyahlothep_outputer_v1`
     system prompt and a `Style` enum (`brief` / `technical` /
     `replication`).
   - `llm_cache.py` provides an in-process cache keyed by
     `(prompt_version, provider, model, report_hash, recipe_hash, style)`
     and stores **validated** output only.
   - `llm_outputer.py` orchestrates generate-validate-cache. Validation
     is strict: missing/extra/wrong-type fields, JSON parse errors, and
     `source_report_id` mismatch all raise `OutputerValidationError`.
     The outputer never mutates the input `selected_report` or
     `replication_recipe`.
   - `POST /advisory/nyahlothep/output` maps each typed exception to a
     visible HTTP status: `OutputerValidationError -> 422`,
     `LLMProviderUnavailable -> 502`, `LLMTimeoutError -> 504`,
     `DisabledLLMClientError -> 503`. There is no silent fallback.
   - Dashboard adds a Nyahlothep narration panel with a style select,
     Generate button gated on a successful wrapper run, status badge
     (ready / generating / cached / error), and a result block that
     renders summary / why_selected / replication_steps / caveats /
     meta-fields entirely via `textContent` (no `innerHTML`, no inline
     handlers, CSP unchanged).
   - Tests: `tests/test_llm_outputer.py` (25 unit tests) and
     `tests/test_api_nyahlothep_output.py` (13 endpoint tests) cover
     happy path, all three styles, cache hit, invalid JSON, missing
     fields, unexpected fields, wrong types, empty steps, source-id
     mismatch, disabled provider, and the no-mutation invariant.
     `tests/test_api.py` adds two dashboard-hookup regressions.

8. Build Azatoth inputer.
   - Reuse the `LLMClient`, `LLMResponseCache`, prompt-versioning, and
     JSON-validation plumbing from V1.
   - Inputer must produce candidate JSON only; every candidate still
     passes through the deterministic filter before selection.
   - Calibrate against the 55-example benchmark — a regression there is
     a verdict regression.

## Suggested Work Order

1. Create a new branch from `main`.

```bash
git switch main
git pull --ff-only origin main
git switch -c codex/report-storage
```

2. Implement one task per PR.
3. Run tests locally before pushing.
4. Push and open a PR.
5. Confirm GitHub Actions before merging.

## Acceptance Criteria For The Next PR

- `python -m pytest projects/effective_boolean_filter/tests/` passes locally.
- GitHub Actions passes on the PR.
- `MANIFEST.json` includes any new tracked files.
- README or project docs mention any new user-facing command or endpoint.
- No public network exposure is introduced without auth and rate limits.
