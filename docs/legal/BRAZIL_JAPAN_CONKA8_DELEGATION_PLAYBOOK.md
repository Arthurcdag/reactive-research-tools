# Brazil-Japan Delegation Playbook

Purpose: allow a Brazil-based owner/operator to delegate legal and monetary
administration to Conka8 in Japan without handing over product control,
customer-data control, IP control, or unlimited signing authority.

This is a business control document, not legal advice. Counsel/accountants in
Brazil and Japan must review the final arrangement before paid launch.

## Delegation Model

| Area | Owner/operator in Brazil | Conka8 in Japan |
|---|---|---|
| Product roadmap | Final authority | Administrative feedback only |
| Customer contracts | Approves templates and terms | Coordinates local review |
| Pricing | Final authority | Reconciles payment/admin costs |
| Payment processor | Approves provider and account owner | Sets up/administers under written authority |
| Bank account | Must belong to correct entity | No personal commingling |
| Taxes/accounting | Chooses accountant and approves filings | Coordinates Japan-side accountant |
| API/customer keys | Product operator controls issuance | No access unless required and logged |
| Customer content | Product operator controls | No access unless DPA and need-to-know exist |

## Authority Limits

Conka8 can be authorized to:

- coordinate with Japan-side counsel, accountants, banks, and payment providers;
- maintain compliance calendars;
- prepare invoice/payment summaries;
- collect KYC/KYB documents from the owner for approved providers;
- report monthly legal/monetary status.

Conka8 should not be authorized to:

- transfer IP;
- borrow money;
- sign long-term contracts;
- change product claims or public pricing;
- access customer reports or API secrets without explicit need;
- mix personal, sealed-company, and second-company funds.

## Operating Workflow

1. Customer pays through the selected processor or invoice route.
2. Conka8 confirms receipt/reconciliation only, not product entitlement.
3. The operator provisions the API key using `scripts/provision_customer_key.py`.
4. Conka8 records invoice/payment metadata, not the secret token.
5. If payment fails, Conka8 notifies operator; operator disables/removes key.
6. Monthly close reconciles processor, bank, invoices, `EBF_API_KEYS`, and
   customer report retention status.

No-secret customer registry:

```bash
python scripts/provision_customer_key.py \
  --customer-id customer-a \
  --plan starter \
  --base-url https://your-domain \
  --registry-file operator_exports/customer_registry.json \
  --payment-reference INV-2026-001 \
  --contracting-entity brazil-entity
```

Conka8-safe reconciliation:

```bash
python scripts/customer_reconciliation.py \
  --registry-file operator_exports/customer_registry.json \
  --output operator_exports/reconciliation-2026-05.md
```

## Brazil Checks

- CNPJ/entity setup through the official business registration path if selling
  from Brazil.
- Receita Federal tax/recordkeeping obligations.
- LGPD controller/operator roles and data-subject request process.
- Brazilian invoice/tax treatment for domestic and cross-border sales.

## Japan Checks

- Whether Japan activity is only administration/contractor support or requires
  branch/subsidiary/representative setup.
- If a Japanese company is formed: registration, tax notifications, corporate
  number, and bank account.
- If Conka8 represents the company: formal authority and liability boundaries.
- If Conka8 handles funds or remittance: payment/funds-transfer regulatory
  review.

## Source Starting Points

- Brazil CNPJ / Redesim:
  https://www.gov.br/empresas-e-negocios/pt-br/redesim/abrir-cnpj
- Receita Federal CNPJ services:
  https://www.gov.br/receitafederal/pt-br/servicos/cadastro/cnpj
- ANPD/LGPD agent definitions:
  https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados-1/titular-de-dados
- Banco Central payment-arrangement references:
  https://www.bcb.gov.br/estabilidadefinanceira/relacaoarranjosintegrantes
- JETRO setting up business in Japan:
  https://www.jetro.go.jp/en/invest/setting_up/
- Japan NTA corporation establishment notifications:
  https://www.nta.go.jp/english/Guidelines.htm
- Japan Companies Act official translation:
  https://www.japaneselawtranslation.go.jp/en/laws/view/4481/en

## Launch Gate

- [ ] Signed Conka8 delegation agreement.
- [ ] Entity and tax path selected.
- [ ] Payment account owner verified.
- [ ] No commingling with sealed-company or IFRS assets.
- [ ] API key process tested without sharing token with Conka8.
- [ ] Monthly reconciliation process assigned.
