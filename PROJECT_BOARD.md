# Project board

## Effective Boolean Filter

### Sprint 1: Core engine
- [x] Repo skeleton
- [x] MVP CLI
- [x] Initial parser
- [x] Initial polarity/scoring engine
- [x] Robust JSON schema
- [x] Negation parity invariants

### Sprint 2: Scope and contradiction
- [x] Scope tracker
- [x] Definition-shift detector
- [x] Contradiction containment
- [x] No-explosion behavior

### Sprint 3: Reactive probes
- [x] Probe generator expansion
- [x] Probe scoring
- [x] Effectiveness-score calibration

### Sprint 4: API/CLI
- [x] FastAPI endpoints
- [x] Report storage
- [x] CLI JSON/human output
- [x] Dashboard

### Sprint 5: Benchmarks
- [x] 50+ case benchmark
- [x] Regression tests
- [x] CI workflow

### Sprint 6: Advisory wrapper
- [x] Azatoth deterministic candidate generation
- [x] Nyahlothep report-based selection
- [x] Advisory API endpoints
- [x] Dashboard wrapper panel
- [x] Nyahlothep/outputer LLM plumbing behind structured validation
- [x] Trace + gate lite provenance for advisory selection
- [x] Opt-in advisory ledger + deterministic replay verification
- [x] Anthropic provider adapter behind shared LLM plumbing
- [x] Azatoth/inputer live LLM candidate generation behind shared plumbing
- [x] No-network advisory provider status/preflight

### Sprint 7: Commercial operations
- [x] Public mode API-key gate
- [x] Dashboard access-key cookie bootstrap
- [x] Per-plan rate limiting
- [x] Commercial plan/status endpoints
- [x] Terms/privacy draft endpoints
- [x] Docker/Render/GHCR deployment path
- [x] Payment provider webhook provisioning (Stripe; signature-verified,
      idempotent ledger, registry mutation)
- [ ] Tenant database for API keys and report retention

### Deferred
- [ ] Full LLM advisory parser/probe wrapper provider integration

## Xi–Jensen Pipeline

### Certification loop
- [x] Fast dashboard runner
- [x] Deepcheck solver
- [x] Certified merge
- [x] Certified merge v2
- [x] Certification status
- [ ] Batch planner
- [ ] Residual-gated certification
- [ ] Publication-grade audit report

### CI coverage
- [x] Xi-Jensen CI smoke coverage (unit, CLI --help, sample-output regression)
