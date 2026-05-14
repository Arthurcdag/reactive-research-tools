#!/usr/bin/env python3
"""Generate a no-secret customer reconciliation report for Conka8/admin use."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_registry(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if data.get("schema") != "rtt_customer_registry_v1":
        raise ValueError("unsupported customer registry schema")
    customers = data.get("customers")
    if not isinstance(customers, list):
        raise ValueError("customer registry must contain a customers list")
    return data


def customer_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in data["customers"]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "customer_id": str(item.get("customer_id", "")),
                "plan": str(item.get("plan", "")),
                "status": str(item.get("status", "")),
                "payment_reference": str(item.get("payment_reference", "")),
                "contracting_entity": str(item.get("contracting_entity", "")),
                "key_fingerprint": str(item.get("key_fingerprint", "")),
                "created_at": str(item.get("created_at", "")),
            }
        )
    return sorted(rows, key=lambda row: (row["status"], row["customer_id"], row["plan"]))


def render_markdown(data: dict[str, Any], *, title: str = "Customer Reconciliation") -> str:
    rows = customer_rows(data)
    by_status = Counter(row["status"] or "unknown" for row in rows)
    by_plan = Counter(row["plan"] or "unknown" for row in rows)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    lines = [
        f"# {title}",
        "",
        f"Generated: {generated_at}",
        "",
        "This report intentionally excludes API tokens and customer content.",
        "",
        "## Summary",
        "",
        f"- Total customers: {len(rows)}",
    ]
    for status, count in sorted(by_status.items()):
        lines.append(f"- {status}: {count}")
    for plan, count in sorted(by_plan.items()):
        lines.append(f"- plan {plan}: {count}")

    lines.extend(
        [
            "",
            "## Customers",
            "",
            "| Customer | Plan | Status | Payment ref | Entity | Key fingerprint | Created |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            "| {customer_id} | {plan} | {status} | {payment_reference} | "
            "{contracting_entity} | {key_fingerprint} | {created_at} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Conka8 Checklist",
            "",
            "- [ ] Reconcile active customer count against paid invoices.",
            "- [ ] Confirm suspended/non-paying customers are removed from EBF_API_KEYS.",
            "- [ ] Confirm bank/payment processor settlement for each payment reference.",
            "- [ ] Report discrepancies to product operator without requesting API tokens.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate customer reconciliation report.")
    parser.add_argument("--registry-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Customer Reconciliation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = load_registry(args.registry_file)
        report = render_markdown(data, title=args.title)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"reconciliation_report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
