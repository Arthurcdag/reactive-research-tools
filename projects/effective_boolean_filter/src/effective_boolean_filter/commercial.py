"""Commercial/legal metadata exposed by the API and docs.

These are product operating defaults, not jurisdiction-specific legal advice.
Before selling in a real jurisdiction, have counsel review the final terms,
privacy notice, invoicing flow, and data-processing obligations.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    slug: str
    name: str
    monthly_usd: int | str
    included: tuple[str, ...]


PLANS = (
    Plan(
        slug="demo",
        name="Demo",
        monthly_usd=0,
        included=(
            "Local/demo use",
            "Low request ceiling",
            "No production warranty",
        ),
    ),
    Plan(
        slug="starter",
        name="Starter API",
        monthly_usd=29,
        included=(
            "API key access",
            "Commercial dashboard access",
            "Standard retention controls",
        ),
    ),
    Plan(
        slug="pro",
        name="Pro Research Ops",
        monthly_usd=149,
        included=(
            "Higher API request ceiling",
            "Advisory wrapper access",
            "Priority operational support",
        ),
    ),
    Plan(
        slug="enterprise",
        name="Enterprise / Sealed Tenant",
        monthly_usd="custom",
        included=(
            "Private deployment",
            "Dedicated API keys and storage boundary",
            "Custom DPA/SLA review",
        ),
    ),
)


TERMS_SUMMARY = """Reactive Research Tools terms summary

The service evaluates argument structure. It is not a truth oracle, legal
advisor, medical advisor, financial advisor, or scientific certifier.
Customers are responsible for final decisions, regulatory compliance, and
review of generated reports before external use.

Accounts/API keys are customer-confidential. Do not share keys across tenants
or between unrelated companies. The operator may suspend keys for abuse,
security risk, non-payment, or unlawful use.
"""


PRIVACY_SUMMARY = """Reactive Research Tools privacy summary

Inputs may contain proprietary research text. Treat claim, argument, context,
probe answer, advisory seed, and generated report fields as customer content.
For production use, configure an explicit report store, retention period,
deletion process, and access-control model before accepting customer data.

The public/commercial deployment must not ingest IFRS institutional records or
sealed-company material unless a written authorization and data-processing
basis exist for that tenant.
"""


def plans_payload() -> dict[str, object]:
    return {
        "currency": "USD",
        "billing_provider": "external_checkout_required",
        "plans": [
            {
                "slug": plan.slug,
                "name": plan.name,
                "monthly_usd": plan.monthly_usd,
                "included": list(plan.included),
            }
            for plan in PLANS
        ],
    }
