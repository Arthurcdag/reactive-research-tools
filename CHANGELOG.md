# Changelog

All notable shipped work on this repository, newest first. This file is the
history record; `docs/DEVELOPER_NEXT_STEPS.md` holds only forward-looking work.

Dates are merge/landing dates on `main`. Entries are grouped by the pull
request that delivered them.

## 2026-05-14 — Commercial operations groundwork

- **Public/commercial mode** (`#16` line): API-key gate (`EBF_PUBLIC_MODE`,
  `EBF_API_KEYS`), dashboard access-key cookie bootstrap, per-plan rate
  limiting, `/commercial/plans` and `/commercial/status`, draft `/legal/terms`
  and `/legal/privacy` endpoints, and a Docker/Render/GHCR deployment path.
- **Customer key provisioning / reconciliation / lifecycle** workflows under
  `scripts/`, plus the `pulse_grab` and `operations` modules.
- **API key fingerprinting** hardened to blake2b derivation.
- Legal source notes and the Brazil–Japan delegation playbook added under
  `docs/`.

## 2026-05-08 — Xi–Jensen CI smoke coverage (#16)

- Added `projects/xi_jensen_pipeline/tests/`: pure-function unit tests, CLI
  `--help` smoke tests, and sample-output regression tests.
- Local `conftest.py` makes the inter-script imports resolve under pytest.
- `pyproject.toml` `testpaths` and the CI workflow now run both project trees.
- The expensive Xi–Jensen workloads stay manual and out of CI scope.

## 2026-05-06 — Advisory provider status / preflight (#15)

- `llm_client.provider_status()` reports fake/Anthropic config readiness with
  no provider request and no credential exposure.
- `GET /advisory/provider/status` plus a dashboard provider-status strip.

## 2026-05-06 — Anthropic provider adapter (#14)

- `EBF_LLM_PROVIDER=anthropic` support over the existing `httpx` dependency,
  no provider SDK.
- Non-streaming Messages API requests at `temperature: 0`; config via
  `ANTHROPIC_API_KEY`, `EBF_LLM_MODEL`, and optional `EBF_ANTHROPIC_VERSION`,
  `EBF_LLM_BASE_URL`, `EBF_LLM_MAX_TOKENS`.
- Missing config / network failure / timeout map to the typed
  `DisabledLLMClientError` / `LLMProviderUnavailable` / `LLMTimeoutError`.

## 2026-05-06 — Advisory ledger + full replay (#13)

- `advisory_ledger.py`: `NullAdvisoryLedger` default, `FileAdvisoryLedger`
  behind `EBF_ADVISORY_LEDGER=file:/path/to/log.jsonl`.
- `/advisory/run` and `/advisory/nyahlothep` append full local snapshots after
  selected-report storage succeeds.
- `GET /advisory/ledger`, `GET /advisory/ledger/{entry_id}`, and
  `POST /advisory/ledger/{entry_id}/replay` verify the append-only hash chain
  and re-run deterministic selection from the stored snapshot.

## 2026-05-06 — Azatoth inputer V1 (#12)

- Bounded monkey/typewriter candidate swarm behind the shared LLM plumbing.
- Separate `InputerCacheKey` shape and `inputer/` cache namespace so seed data
  is never treated as a report.
- `POST /advisory/azatoth/input`; `/advisory/run` gains optional
  `source ∈ {deterministic, inputer}` and `pool_size`.
- The deterministic engine remains the only verdict source.

## 2026-05-05 — Advisory trace + gate lite (#11)

- `trace_gate.py`: deterministic `PipelineTrace` stages and promotion /
  reality-gate receipts for advisory provenance.
- `/advisory/run` and `/advisory/nyahlothep` gain additive `trace` and `gates`
  metadata; the dashboard shows it downstream of selection.

## 2026-05-03 — Nyahlothep outputer V1 (#10)

- `llm_client.py` (`LLMClient` interface, `DeterministicFakeClient` default,
  provider slot behind `EBF_LLM_PROVIDER`), `llm_prompts.py`, `llm_cache.py`,
  and `llm_outputer.py` orchestrating generate → validate → cache.
- `POST /advisory/nyahlothep/output` with typed-exception → HTTP status
  mapping and no silent fallback.
- Dashboard narration panel rendered entirely via `textContent`.

## 2026-05-03 — Advisory wrapper V0 (#9)

- `advisory.py`: deterministic contract where Azatoth generates a bounded
  candidate swarm, the filter evaluates each candidate, and Nyahlothep selects
  from filter reports only.
- `POST /advisory/azatoth`, `POST /advisory/nyahlothep`, `POST /advisory/run`,
  plus a compact dashboard wrapper panel. No provider keys or network calls.

## 2026-05-03 — Dashboard UX + public deployment checklist (#7, #8)

- Sample-preset buttons, score-vector table, and a CSP-safe Copy JSON action.
- `docs/PUBLIC_DEPLOYMENT_CHECKLIST.md` covering auth, rate limiting, HTTPS,
  CORS, logging, data retention, and pre-launch verification.

## 2026-05-02 — Report storage, API error tests, CI bump (#4, #5, #6)

- `storage.py`: `InMemoryStore` default and `FileStore` selected via
  `EBF_REPORT_STORE`; round-trip persistence covered in tests.
- `tests/test_api_validation.py`: 52-test negative-path / CSP / security-header
  coverage.
- CI bumped `actions/checkout@v6` and `actions/setup-python@v6` (Node 24).

## 2026-04-30 — Effective Boolean Filter dashboard + developer docs (#2, #3)

- Browser dashboard served with a restrictive CSP and localhost binding.
- `docs/DEVELOPER_NEXT_STEPS.md` introduced.

## 2026-04-29 — Effective Boolean Filter MVP (#2)

- Sprints 1–5: parser, polarity/scoring engine, scope tracker,
  definition-shift detector, contradiction containment, reactive probes,
  FastAPI surface, CLI, and a 50+ case benchmark with regression tests.

## 2026-04-28 — Repository bootstrap (#1)

- Initial README, requirements, gitignore, pytest config, project board, and
  the Xi–Jensen research toolchain (`projects/xi_jensen_pipeline/`).
