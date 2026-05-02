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

2. Improve dashboard usability without adding a frontend build step.
   - Add sample presets for common cases: clean double negation, epistemic
     shift, scope shift, contained contradiction.
   - Add a compact score-vector table.
   - Add a copy JSON button only if clipboard usage is explicit and visible.

3. ~~Add API error tests.~~ ✅ Shipped on branch `codex/api-error-tests`.
   - `tests/test_api_validation.py` (52 tests) covers: over-length
     claim/argument/context/task/probe-answer bodies, the strictness
     whitelist (case-sensitive, with wrong-type rejection), malformed
     probe answers (missing fields, wrong types, empty question,
     non-list `answers`), generic missing/non-JSON/wrong-type bodies,
     CSP regression (all 7 directives + per-response nonce + cache),
     extra security headers, middleware coverage on non-dashboard
     endpoints, plus 404/405 surface.

4. Add a public-sharing deployment checklist.
   - Include auth, rate limiting, logging, data retention, HTTPS, and CORS.
   - Document that current dashboard is safe for local demo/source sharing, not
     open internet deployment.

5. Address GitHub Actions maintenance.
   - GitHub warned that Node.js 20 actions are deprecated.
   - Check for newer versions of `actions/checkout` and `actions/setup-python`
     or test the Node 24 opt-in setting in a separate PR.

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
