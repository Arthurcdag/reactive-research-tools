# Operations and Monetization

This repo can now run as a public, API-key-gated service while remaining
separate from IFRS workspaces and any sealed-company material.

## Separation Rule

Keep three boundaries separate:

- IFRS/public-sector work stays in its own workspace, accounts, storage, and
  authorization chain.
- Any sealed company stays sealed: no names, files, private strategy, keys,
  customer data, or internal notes should be copied into this repo.
- The commercial Reactive Research Tools service uses its own GitHub repo,
  hosting account, domain, payment account, API keys, and report storage.

Do not use institutional files, private research notes, or customer content as
demo data unless that tenant has written authorization and a data-processing
basis.

## Public Service Configuration

Required production variables:

```text
EBF_PUBLIC_MODE=1
EBF_API_KEYS=<key-id>:<plan>:<secret-token>
EBF_REPORT_STORE=file:/data/reports
```

Supported API key formats:

```text
<secret-token>
<key-id>:<secret-token>
<key-id>:<plan>:<secret-token>
```

Clients can authenticate with either:

```text
Authorization: Bearer <secret-token>
X-API-Key: <secret-token>
```

Browser customers can open the dashboard once with:

```text
https://your-domain/?access_key=<secret-token>
```

The server sets an HttpOnly cookie so later same-origin dashboard calls are
authenticated without putting the key in JavaScript.

## Plans

The API exposes plan metadata at:

```text
GET /commercial/plans
GET /commercial/status
```

Default commercial tiers:

- `demo`: local or low-volume demo.
- `starter`: paid dashboard/API access.
- `pro`: higher API ceiling and advisory-wrapper usage.
- `enterprise`: private tenant, custom DPA/SLA, dedicated storage boundary.

Rate limits are per API key fingerprint. Defaults can be overridden:

```text
EBF_PLAN_LIMITS=starter=120/minute,pro=600/minute,enterprise=1800/minute
```

## Billing Flow

Billing is intentionally external in this version.

1. Customer pays through Stripe, Mercado Pago, invoice, or another processor.
2. Operator provisions an API key with the paid plan.
3. Customer receives the dashboard URL and API key.
4. Failed payment or cancellation means the key is removed or rotated.

Do not put payment secrets in this repo. Store processor keys only in the
hosting provider secret manager.

Provision a key:

```bash
python scripts/provision_customer_key.py \
  --customer-id customer-a \
  --plan starter \
  --base-url https://your-domain \
  --registry-file operator_exports/customer_registry.json \
  --payment-reference INV-2026-001 \
  --contracting-entity brazil-entity \
  --monthly-amount 29 \
  --currency BRL
```

The command prints an `EBF_API_KEYS` entry and a one-time dashboard bootstrap
URL. Store the generated token in a password vault or hosting secret manager.
Generated local files such as `secrets/` and `customer_keys*.env` are ignored by
Git.

Update customer lifecycle state without exposing tokens:

```bash
python scripts/customer_lifecycle.py \
  --registry-file operator_exports/customer_registry.json \
  --customer-id customer-a \
  --status suspended \
  --note "payment failed"
```

Use the same command for paid reactivation, cancellation, plan changes, payment
references, and amount changes:

```bash
python scripts/customer_lifecycle.py \
  --registry-file operator_exports/customer_registry.json \
  --customer-id customer-a \
  --status active \
  --plan pro \
  --payment-reference INV-2026-002 \
  --monthly-amount 79 \
  --currency BRL \
  --note "upgraded after invoice payment"
```

Generate a no-secret reconciliation report for Conka8:

```bash
python scripts/customer_reconciliation.py \
  --registry-file operator_exports/customer_registry.json \
  --output operator_exports/reconciliation-2026-05.md \
  --title "Conka8 Reconciliation 2026-05"
```

The reconciliation report includes customer IDs, plan names, payment
references, monthly amount by currency, entity labels, lifecycle status, and
token fingerprints. It intentionally excludes API tokens and customer report
content.

Customer offboarding:

1. Mark the registry entry `suspended` or `canceled` with
   `scripts/customer_lifecycle.py`.
2. Remove the customer's entry from `EBF_API_KEYS`.
3. Restart/redeploy the service.
4. Confirm `GET /commercial/status` returns `401` for that key.
5. Apply the retention/deletion policy for the customer's reports.

## Brazil-Japan Delegation

If Conka8 administers legal or monetary work from Japan, keep that role
administrative and bounded. Conka8 can coordinate counsel, accounting, payment
providers, and reconciliation, but should not receive unrestricted signing
authority, product control, customer-content access, or API secret custody.

See [`docs/legal/BRAZIL_JAPAN_CONKA8_DELEGATION_PLAYBOOK.md`](legal/BRAZIL_JAPAN_CONKA8_DELEGATION_PLAYBOOK.md).

## Pulse Grab Security

For actions that touch money, API secrets, legal terms, customer content, or
public claims, use Pulse Grab as an execution hold instead of deleting possible
actions from the workflow. A held action can proceed once its missing controls
are supplied.

See [`docs/security/PULSE_GRAB_SECURITY.md`](security/PULSE_GRAB_SECURITY.md).

## Deploy

Render:

1. Connect this GitHub repo.
2. Use the included `render.yaml`.
3. Let Render generate `EBF_API_KEYS`, or replace it with a planned key:
   `customer-a:starter:<long-random-secret>`.
4. Confirm `/health` returns `{"status":"ok"}`.
5. Open `/?access_key=<secret-token>` once in the browser.

Container:

```bash
docker build -t reactive-research-tools .
docker run --rm -p 8000:8000 \
  -e EBF_PUBLIC_MODE=1 \
  -e EBF_API_KEYS=local:starter:dev-secret \
  -e EBF_REPORT_STORE=file:/data/reports \
  -v ebf-reports:/data \
  reactive-research-tools
```

## Remaining Launch Work

- Review final Terms of Service and Privacy Notice with counsel.
- Choose payment processor and invoice/tax flow.
- Add a key-provisioning database or admin UI once the JSON registry becomes
  operationally awkward.
- Decide retention period and deletion workflow for persisted reports.
- Put TLS, access logs, and backups under the hosting provider runbook.
