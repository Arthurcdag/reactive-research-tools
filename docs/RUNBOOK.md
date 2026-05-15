# Production Runbook

## Health

```bash
curl https://your-domain/health
```

Expected:

```json
{"status":"ok"}
```

## Customer Access Check

```bash
curl https://your-domain/commercial/status \
  -H "X-API-Key: <customer-token>"
```

Expected fields:

- `authenticated: true`
- `key_id`
- `plan`
- `fingerprint`

## Rotate a Key

1. Generate a replacement token.
2. Update `EBF_API_KEYS` in the hosting secret manager.
3. Redeploy or restart the service.
4. Send the customer the new dashboard bootstrap URL.
5. Remove the old key after the cutover window.

Generate the replacement:

```bash
python scripts/provision_customer_key.py \
  --customer-id customer-a \
  --plan starter \
  --base-url https://your-domain
```

Never paste old or new tokens into public issues, commits, screenshots, or
support messages.

Before rotating a production key, a Pulse Grab receipt should show
`secret_vault_change_review` as supplied.

## Suspend, Reactivate, or Cancel a Customer

The no-secret registry records lifecycle state for Conka8/admin reconciliation.
It does not replace `EBF_API_KEYS`; service access changes only after the
hosting secret is updated and redeployed.

Suspend after failed payment:

```bash
python scripts/customer_lifecycle.py \
  --registry-file operator_exports/customer_registry.json \
  --customer-id customer-a \
  --status suspended \
  --note "payment failed"
```

Reactivate or upgrade after payment:

```bash
python scripts/customer_lifecycle.py \
  --registry-file operator_exports/customer_registry.json \
  --customer-id customer-a \
  --status active \
  --plan pro \
  --payment-reference INV-2026-002 \
  --monthly-amount 79 \
  --currency BRL
```

Cancel:

```bash
python scripts/customer_lifecycle.py \
  --registry-file operator_exports/customer_registry.json \
  --customer-id customer-a \
  --status canceled \
  --monthly-amount 0 \
  --note "customer requested cancellation"
```

Before disabling access for non-payment, a Pulse Grab receipt should include
`finance_approval`, `payment_reference`, and `operator_approval`.

## Incident Checklist

- Disable or rotate suspected keys.
- Preserve logs without request bodies.
- Confirm `/commercial/status` returns `401` for the disabled token.
- Notify affected customers if content exposure is plausible.
- Record timeline, affected tenant, root cause, and corrective action.

## Backup and Restore

For `EBF_REPORT_STORE=file:/data/reports`, back up `/data/reports` at the
provider level. Test restore into a staging instance before relying on it for
customer commitments.

The webhook registry and ledger should be backed up the same way:

- `EBF_CUSTOMER_REGISTRY` — the source of truth for plan / status state.
- `EBF_PAYMENT_WEBHOOK_LEDGER` — the dedupe + audit log. Loss of this
  file means the next Stripe re-delivery will re-apply already-applied
  events; restore it before re-enabling the endpoint after an incident.
- `EBF_TENANT_DB` — the SQLite tenant database. Single file; back it up
  with the same cadence as the report store. SQLite's `.backup` CLI is
  the simplest live-backup mechanism; or shut the service for the
  snapshot, copy the file, restart.

## Tenant Database

Open it from any operator shell:

```bash
sqlite3 /data/tenant.sqlite ".schema"
sqlite3 /data/tenant.sqlite \
    "SELECT tenant_id, plan, status FROM tenants ORDER BY tenant_id;"
```

Routine operations go through the admin CLI rather than raw SQL — see
[OPERATIONS_AND_MONETIZATION.md](OPERATIONS_AND_MONETIZATION.md). The
CLI is also the right place for incident response:

```bash
# Disable a key immediately (cheaper than redeploying EBF_API_KEYS)
python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
    keys revoke --key-id customer-a-12345678

# Audit what a customer is paying for and which keys are active
python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
    keys list --tenant-id customer-a
```

Before revoking a production key, a Pulse Grab receipt should show
`secret_vault_change_review` as supplied. Treat the DB file itself as a
secret-grade artefact — its rows include token hashes and tenant
payment references.

## Payment Webhook

The webhook is **off by default**. Enable it in production with both:

```text
EBF_STRIPE_WEBHOOK_SECRET=whsec_...
EBF_CUSTOMER_REGISTRY=/data/customer_registry.json
EBF_PAYMENT_WEBHOOK_LEDGER=/data/payment_webhook_ledger.jsonl
```

### Verify the endpoint is live (no secret needed)

```bash
curl -i -X POST https://your-domain/commercial/webhook/stripe
```

Expected when not configured: `503` with `detail` mentioning
`EBF_STRIPE_WEBHOOK_SECRET`. Expected when configured but unsigned:
`401` with `detail` `Stripe-Signature missing` or similar.

### Stripe configuration checklist

1. Create a webhook endpoint in the Stripe dashboard at
   `https://your-domain/commercial/webhook/stripe`.
2. Subscribe to the events listed in
   [`OPERATIONS_AND_MONETIZATION.md`](OPERATIONS_AND_MONETIZATION.md).
3. Copy the signing secret (`whsec_...`) into the hosting secret manager
   as `EBF_STRIPE_WEBHOOK_SECRET`. Never commit it.
4. On every subscription (or Checkout Session) set
   `metadata.customer_id` to the local registry slug and either set
   `metadata.plan` or set the price `lookup_key` to the plan slug
   (`demo` / `starter` / `pro` / `enterprise`).

### Reading the ledger

The ledger is append-only JSONL keyed on `(provider, event_id)`. Each
line is an `EventApplication` record. Useful one-liners:

```bash
# Count outcomes by action over the file
jq -r .action /data/payment_webhook_ledger.jsonl | sort | uniq -c

# Recent rejections for an operator to fix in Stripe
jq -c 'select(.action | startswith("rejected"))' /data/payment_webhook_ledger.jsonl

# Replay safety: confirm event_id was applied exactly once
grep '"event_id":"evt_..."' /data/payment_webhook_ledger.jsonl
```

### Webhook delivery failure

Stripe retries non-2xx responses with exponential backoff. If you see
4xx/5xx clusters in Stripe's dashboard, check:

- `503` — `EBF_STRIPE_WEBHOOK_SECRET` or `EBF_CUSTOMER_REGISTRY` is unset.
- `401` — secret rotated in Stripe but not in our env, or clock skew
  exceeds the tolerance (default 300 s).
- `400` — Stripe event payload is missing `metadata.customer_id` for a
  non-ignored event type. Fix the Stripe subscription metadata and
  resend the event from the Stripe dashboard.
- `500` — registry file is malformed or unreachable. Fix the registry
  and Stripe will redeliver.

A `200` response with `applied: false, action: "rejected_no_customer"`
means the Stripe `customer_id` metadata points at a slug that does not
exist in our registry. Provision the customer first
(`scripts/provision_customer_key.py`), then resend the Stripe event.

Before changing the webhook secret in production, a Pulse Grab receipt
should show `secret_vault_change_review` as supplied.
