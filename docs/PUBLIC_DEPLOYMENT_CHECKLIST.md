# Public Deployment Checklist

Use this checklist before exposing the Effective Boolean Filter API or
dashboard to anyone outside `127.0.0.1`. Every section is a hard
prerequisite for public exposure unless explicitly marked optional.

> **Current posture.** The default configuration — `uvicorn ... --host
> 127.0.0.1`, `EBF_REPORT_STORE=memory`, no auth, no rate limit — is
> safe **only** for local demos and code-share screenshots on the
> developer's own machine. It is not safe to bind to `0.0.0.0` or
> place behind a public domain without completing the items below.

## Implemented baseline controls

The FastAPI app now includes an opt-in public/commercial mode:

```text
EBF_PUBLIC_MODE=1
EBF_API_KEYS=<key-id>:<plan>:<secret-token>
EBF_REPORT_STORE=file:/data/reports
```

Implemented:

- API-key auth via `Authorization: Bearer <token>` or `X-API-Key`.
- Dashboard cookie bootstrap via `/?access_key=<token>`.
- Docs/OpenAPI disabled by default in public mode.
- In-memory per-key/per-plan fixed-window rate limits.
- Public commercial/legal metadata endpoints.
- Dockerfile, Render blueprint, pinned `requirements-lock.txt`, and GHCR
  container publishing workflow.

Still external to this codebase:

- TLS termination and HSTS at the host/proxy.
- Payment processor checkout and tax/invoicing flow.
- Final Terms/Privacy review by counsel.
- Backup, deletion, and retention operations for each tenant.

## 1. Authentication

Public mode now has API-key authentication. The default local mode still has
anonymous access for developer demos; that is intentional locally and
unacceptable for the public internet.

- [x] Decide on an auth model: API key (machine-to-machine) plus cookie
      bootstrap for the browser dashboard.
- [x] Add an auth dependency at the FastAPI layer.
- [x] Reject unauthenticated requests with `401`, not `403` or `200`.
- [x] Apply auth uniformly to every endpoint in public mode: `POST /evaluate_argument`,
      `POST /generate_probes`, `POST /score_probe_results`,
      `GET /reports/{id}`, including `GET /` (dashboard).
- [ ] Rotate API keys / revoke tokens out of band; do not commit
      keys to the repo.
- [ ] Log auth failures (with rate of failures), not auth successes
      with credentials.

## 2. Rate limiting

Pydantic enforces per-request body size (claim ≤ 4000, argument ≤
8000, context ≤ 2000, task ≤ 500, ≤ 20 probe answers). That is not
the same as request-rate limiting — a single client can still flood
the engine with full-size requests.

- [x] Public-mode anonymous requests are blocked before engine endpoints.
- [x] Per-identity rate limit on authenticated requests, separately
      tracked by key fingerprint and plan.
- [ ] Stricter ceilings on `POST /evaluate_argument` and
      `POST /score_probe_results` (engine work) than on
      `POST /generate_probes` (cheap parse-only).
- [ ] A request-body size cap at the proxy layer — recommended
      8 KB for `/generate_probes`, 32 KB for the others — so an
      attacker cannot keep Pydantic busy parsing a 10 MB payload
      that would have been rejected anyway.
- [x] Document the limits publicly so legitimate clients know what
      to expect; emit `Retry-After` on `429` responses.

## 3. HTTPS

- [ ] Terminate TLS at a reverse proxy. Do not run uvicorn with
      `--ssl-keyfile` directly on a public interface; use a proxy
      that handles cert renewal (Caddy, Traefik, nginx + certbot).
- [ ] TLS 1.2 or higher only.
- [ ] HSTS header on every response from the proxy:
      `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- [ ] Auto-renewal verified end-to-end before going live.
- [ ] Redirect any `http://` request to `https://` at the proxy.

## 4. CORS

There is no CORS middleware in `api.py`. Same-origin browser
requests work (the dashboard at `GET /` calls `/evaluate_argument`
on the same host). Cross-origin browser clients are blocked by the
browser's same-origin policy.

- [ ] If you intentionally expose the API to other origins, add
      `fastapi.middleware.cors.CORSMiddleware` with an explicit
      allow-list of origins. **Do not** use `allow_origins=["*"]`.
- [ ] `allow_credentials=True` only when the auth model needs it
      (cookies); otherwise leave it `False`.
- [ ] Restrict `allow_methods` to the methods actually used on each
      endpoint (`POST` and `GET`). Do not `allow_methods=["*"]`.
- [ ] `allow_headers` should match the headers your clients send
      (`Content-Type`, optional `Authorization`); do not wildcard.
- [ ] Re-check the CSP `connect-src` directive on the dashboard if
      the dashboard ever needs to call a different origin (it
      currently does not).

## 5. Logging

User input is sensitive. The current default (uvicorn access logs)
already keeps request bodies out of the log; verify before adding
any custom logging.

- [ ] Never log the `claim`, `argument`, `context`, or
      `probe_answers.answer` fields. They may contain proprietary
      hypotheses, internal incident text, or personal data.
- [ ] Log report IDs, polarity, recommendation, effectiveness
      score, and bogusness score — those are non-sensitive and
      useful for monitoring.
- [ ] Log auth events (success/failure) with the **identity**, not
      with the credential.
- [ ] Use structured JSON logs (`uvicorn --log-config logging.json`
      or `structlog`) so a log-aggregation tool can filter by
      field.
- [ ] Log rotation + retention policy in line with section 6.
- [ ] Disable FastAPI's `/docs` and `/redoc` Swagger surfaces in
      production unless they are gated behind auth — they are
      currently default-on and reveal full endpoint shapes.
- [ ] Configure the proxy access log to drop request bodies.

## 6. Data retention

The API stores evaluation reports via a swappable
[`ReportStore`](../projects/effective_boolean_filter/src/effective_boolean_filter/storage.py).
`InMemoryStore` is ephemeral — fine for a demo, no retention
problem. `FileStore` is durable and accumulates indefinitely.

- [ ] Decide an explicit retention period (e.g. 30 days for
      `FileStore`-backed reports). Document it in your privacy
      notice.
- [ ] Implement a cron / systemd timer / scheduled job that
      deletes reports older than the retention window. The
      `FileStore.list_ids()` and `FileStore._path()` are enough to
      build it.
- [ ] If you operate in a regulated environment (GDPR, HIPAA,
      etc.), encrypt the `FileStore` root at rest (filesystem-level
      encryption, e.g. LUKS / BitLocker, or per-file via
      `cryptography`).
- [ ] Provide a deletion path: a tracked record can be deleted via
      a simple `os.remove` on its file. Expose this as a deletion
      endpoint **gated by auth** if user-facing deletion is
      required.
- [ ] Document where reports live, who can read them, and how to
      request deletion.

## 7. Network exposure

- [ ] Keep `--host 127.0.0.1` on the FastAPI process. The reverse
      proxy listens on `0.0.0.0` and forwards to localhost.
- [ ] Run uvicorn as a non-root user, in a sandboxed unit
      (systemd `ProtectSystem=strict`, container, or jail).
- [ ] Set resource limits (CPU, RAM, file descriptors) — a runaway
      probe loop or large argument should not exhaust the host.
- [ ] If `EBF_REPORT_STORE=file:/some/dir`, that directory must be
      writeable but the rest of the filesystem should be read-only
      to the service account.

## 8. Dependency hygiene

- [ ] Pin every dependency in `requirements.txt` to a specific
      version, not a range.
- [ ] Subscribe the repo to Dependabot or run `pip-audit` on a
      schedule. The CI workflow is the natural place to fail
      builds on known CVEs.
- [ ] Patch within 7 days for high-severity advisories on FastAPI,
      Starlette, Pydantic, and uvicorn.

## 9. Engine integrity

These are repeated from `DEVELOPER_NEXT_STEPS.md`'s safety notes
because they apply equally to public deployments.

- [ ] The deterministic engine remains authoritative. Any LLM
      feature added later must be advisory only and must round-trip
      through structured-JSON validation before its output influences
      a report.
- [ ] Treat every `claim`, `argument`, and `probe_answer` field as
      untrusted. The dashboard renders evaluated content via
      `textContent`, never `innerHTML`. The CSP regression tests
      lock this in; do not weaken `default-src 'none'`.
- [ ] Do not echo user input back into HTTP error messages
      verbatim — Pydantic's default error shape is fine; custom
      error handlers must not reflect raw input.

## 10. Pre-launch verification

Before flipping the DNS record:

- [ ] All eight security headers present on every endpoint
      (`X-Content-Type-Options`, `Referrer-Policy`,
      `Permissions-Policy`, plus the dashboard's CSP and
      `Cache-Control: no-store`).
- [ ] `/docs` and `/redoc` either disabled or auth-gated.
- [ ] Synthetic 401/403/429 probes return the right status codes.
- [ ] A dry-run incident: revoke an API key, confirm clients see
      `401`, restore.
- [ ] A dry-run rotation of TLS certs.
- [ ] Backup + restore of the `FileStore` directory tested.
- [ ] Runbook documented: who pages on what, where logs live, how
      to roll back.

## 11. Reasonable scope today

If the only goal is to share a screenshot or a screen recording
with another developer, **none of the above is required** — the
local-only configuration on `127.0.0.1` is already safe. The
checklist applies the moment any of the following is true:

- The service is reachable from a network beyond your machine.
- More than one person can hit it simultaneously.
- Reports persist on disk in a way other tenants can read.
- The host has a public DNS name.

When in doubt, keep the bind on `127.0.0.1` and use SSH port
forwarding (`ssh -L 8000:127.0.0.1:8000 host`) to share the
running instance with one other person, not a reverse proxy.
