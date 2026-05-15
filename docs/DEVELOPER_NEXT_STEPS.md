# Developer Next Steps

Forward-looking work only. Shipped history lives in
[`../CHANGELOG.md`](../CHANGELOG.md); sprint status lives in
[`../PROJECT_BOARD.md`](../PROJECT_BOARD.md).

## Local Setup

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                # runs both project test trees
```

Run the dashboard locally:

```bash
python -m uvicorn effective_boolean_filter.api:app \
  --app-dir projects/effective_boolean_filter/src \
  --host 127.0.0.1 \
  --port 8000
```

Open `http://127.0.0.1:8000/`.

## Safety Notes (carry-over invariants)

- Treat all evaluated claims and arguments as untrusted input.
- The dashboard must render evaluated content as text, never HTML
  (`textContent` only, no inline handlers, CSP unchanged) — this is a CI
  invariant.
- The deterministic engine must remain the only verdict source. Any LLM
  feature is advisory only and must pass structured JSON validation before
  entering reports.
- Visible-failure policy: typed exceptions map to distinct HTTP statuses, no
  silent fallback.
- Do not expose the API beyond `--host 127.0.0.1` without `EBF_PUBLIC_MODE`
  auth, rate limiting, and a body-size limit in front of it. See
  [`PUBLIC_DEPLOYMENT_CHECKLIST.md`](PUBLIC_DEPLOYMENT_CHECKLIST.md).

## Open Work

### Effective Boolean Filter

- **Payment provider webhook provisioning.** Wire a payment webhook into the
  public-mode customer lifecycle so plan changes are not manual.
- **Tenant database for API keys and report retention.** Replace the env-var
  key list and file report store with a real per-tenant backend.
- **Full LLM advisory parser/probe wrapper provider integration** (deferred).
  Currently only the inputer/outputer paths use a live provider.
- **Engine coverage parity.** The wrapper has grown faster than the engine;
  keep new adversarial benchmark cases (scope-shift bridges, contradiction
  containment edges) landing alongside any wrapper PR.

### Xi–Jensen Pipeline

- **Batch planner**, **residual-gated certification**, and a
  **publication-grade audit report** — the three open items in the
  certification loop on `PROJECT_BOARD.md`.

## Working Agreement

1. Branch from `main`, one logical change per PR.
2. `python -m pytest` passes locally before pushing.
3. `MANIFEST.json` includes any new tracked files.
4. README / project docs mention any new user-facing command or endpoint, and
   the README "Public surface" table is updated for any endpoint change.
5. No public network exposure without auth and rate limits.
6. Move shipped items into `CHANGELOG.md`; keep this file forward-looking.
