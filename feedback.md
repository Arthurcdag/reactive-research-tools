# Feedback on repo state and where to evolve next

## What's working well

- **Visible-failure policy** (typed exceptions -> distinct HTTP statuses, no silent fallback) is solid and rare. Worth keeping as a hard rule going forward.
- **Engine never depends on the LLM stack.** Adapter, ledger, trace/gate are all additive. Good separation.
- **Inputer and outputer have separate cache-key shapes** (different fields + `inputer/` prefix). Correct - prevents seed data being treated as a report.
- **Dashboard uses `textContent` only**, no inline handlers, CSP unchanged. Should stay a CI invariant.

## Things I'd flag

1. **The advisory/LLM stack is now bigger than the deterministic engine** (~2300 LOC vs ~1800 LOC). The project description says *"a traceable argument-effect filter, not a truth oracle."* Worth deciding if the center of gravity is the engine or the wrapper - otherwise every new PR will keep growing the wrapper by default.

2. **`DEVELOPER_NEXT_STEPS.md` is now a graveyard, not a roadmap.** All 11 tasks ✅. Two tasks are both numbered `9`. I'd suggest moving shipped items to a new `CHANGELOG.md` and keeping `DEVELOPER_NEXT_STEPS.md` as a short forward-looking doc only.

3. **Endpoint surface (15 endpoints) has no public-vs-internal boundary documented.** Some overlap - `/advisory/run` already orchestrates the inputer + filter + outputer. Before the next endpoint is added I'd like to add a *"Public surface"* section to the README so callers know what's stable.

4. **No live-provider test.** The Anthropic adapter is unit-tested only with injected fakes. If the real Messages API changes shape, nothing in CI catches it. Cheap fix: one `@pytest.mark.live` test gated on `ANTHROPIC_API_KEY`, skipped in default CI.

5. **Deployment story still blocks at localhost.** Auth, rate limiting, body-size limits - listed in the public deployment checklist but none implemented. If the project is meant to be reachable beyond `--host 127.0.0.1`, this is the biggest gap right now.

6. **`dashboard.py` is ~1200 lines of HTML/JS embedded in a Python string.** Diffs are noisy and reviewing it is getting harder. Splitting the template into its own file (with nonce substitution) would make the next dashboard PR readable.

7. **`xi_jensen_pipeline/` is dormant.** ~30 scripts, README files, no tests, no CI. Worth deciding: bring it under CI, archive it, or move it out. Half-alive in the same repo hides what's load-bearing.

8. **Engine coverage stayed flat while the wrapper doubled.** Benchmark is still 55 examples. Worth one PR for adversarial coverage (scope-shift bridges, contradiction containment edges) before the next wrapper PR.

## Suggested next priorities

1. **Roadmap reset** - move shipped items to `CHANGELOG.md`, fresh `DEVELOPER_NEXT_STEPS.md`.
2. **Public surface README section.**
3. **Live-provider smoke test** (opt-in).
4. **Auth + rate limiting** - simplest credible option (e.g. bearer-token FastAPI dependency + per-IP bucket).
5. **Benchmark expansion.**
6. **`dashboard.py` template split.**
7. **Decision on `xi_jensen_pipeline`.**

Let me know which direction you want to go and I'll pick up the first task.
