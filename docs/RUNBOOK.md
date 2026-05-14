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
