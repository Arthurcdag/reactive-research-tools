# Privacy Notice Draft

This is an operator draft for review by qualified counsel before paid launch.

## Data Processed

The service may process:

- account and billing contact details handled by the payment provider;
- API key identifiers and plan metadata;
- customer-submitted claim, argument, context, probe answer, and advisory seed
  text;
- generated reports, scores, traces, and advisory selections;
- operational metadata such as request timestamp, endpoint, status code, rate
  limit result, and report ID.

## Data Not Needed

The service should not collect passwords, government IDs, payment card data,
health records, student records, or institutional IFRS records unless a separate
written agreement and compliance basis exist.

## Storage and Retention

Production deployments should use `EBF_REPORT_STORE=file:/data/reports` or a
tenant-specific database. The operator must define retention before accepting
customer content. A common starting point is 30 days for standard reports unless
the customer requests earlier deletion or buys an enterprise retention term.

## Access

Access to customer content should be limited to the operator and authorized
support personnel. API keys must be stored as secrets in the hosting provider,
not in the repository.

## Subprocessors

List hosting, payment, email, logging, backup, and optional LLM providers here
before launch. If a live LLM provider is enabled, disclose whether customer text
is sent to that provider.

## Customer Requests

Provide a support email or portal for deletion, export, correction, and
security requests before paid launch.
