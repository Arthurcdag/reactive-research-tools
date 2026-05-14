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
