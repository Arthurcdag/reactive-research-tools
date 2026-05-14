# Pulse Grab Security

Pulse Grab is an execution-hold control for operational actions. It does not
delete possible actions from a workflow. Instead, it holds high-risk execution
until the required approvals, receipts, or custody controls are present.

Portuguese shorthand: `segurar o pulso`. The system lets the hand remain
available, but stops the movement before irreversible impact.

## Where It Fits

Use Pulse Grab for actions that can affect customers, money, legal promises,
API secrets, public claims, or sealed-company boundaries.

It is separate from the Effective Boolean Filter. The filter evaluates claims.
Pulse Grab evaluates whether an operational action can execute now.

## Decision Model

Inputs:

- action identifier;
- whether the action is irreversible;
- whether it touches secrets, customer content, money, legal terms, or public
  publication;
- supplied controls such as `operator_approval`, `finance_approval`,
  `payment_reference`, `counsel_review`, `secret_vault_change_review`, or
  `customer_data_need_to_know`.

Outputs:

- `allow` when required controls are present;
- `hold` when controls are missing;
- risk level, reasons, required controls, missing controls, and an evidence
  hash.

## Commercial Examples

Paid customer provision:

- risk: touches secrets;
- required control: `secret_vault_change_review`;
- result: hold until the generated token is stored in the approved vault and
  never sent to Conka8.

Failed payment suspension:

- risk: money and customer entitlement;
- required controls: `finance_approval`, `payment_reference`,
  `operator_approval`;
- result: hold until invoice/payment evidence exists, then update
  `customer_registry.json`, remove the key from `EBF_API_KEYS`, and redeploy.

Public pricing change:

- risk: public publication and possible legal terms impact;
- required controls: `operator_approval`, `counsel_review`;
- result: hold until owner approval and counsel review are recorded.

## Python Primitive

```python
from effective_boolean_filter import evaluate_pulse_grab

decision = evaluate_pulse_grab(
    action_id="rotate-customer-secret",
    touches_secrets=True,
    supplied_controls=("secret_vault_change_review",),
)
assert decision.status == "allow"
```

Use the returned `evidence_hash` as the receipt in audit logs or runbooks.
