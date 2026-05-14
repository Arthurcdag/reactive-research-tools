#!/usr/bin/env python3
"""Manage no-secret customer lifecycle state.

This updates the customer registry used for Conka8/admin reconciliation. It
never stores API tokens and never touches customer report content.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


VALID_STATUSES = {"active", "suspended", "canceled"}
VALID_PLANS = {"demo", "starter", "pro", "enterprise"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_monthly_amount(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        amount = Decimal(stripped)
    except InvalidOperation as exc:
        raise ValueError("monthly amount must be a number") from exc
    if amount < 0:
        raise ValueError("monthly amount must be zero or greater")
    return format(amount.quantize(Decimal("0.01")), "f")


def normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if currency and (len(currency) != 3 or not currency.isalpha()):
        raise ValueError("currency must be a 3-letter ISO code")
    return currency


def load_registry(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if data.get("schema") != "rtt_customer_registry_v1":
        raise ValueError("unsupported customer registry schema")
    if not isinstance(data.get("customers"), list):
        raise ValueError("customer registry must contain a customers list")
    return data


def save_registry(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


def find_customer(data: dict[str, Any], customer_id: str) -> dict[str, Any]:
    for item in data["customers"]:
        if isinstance(item, dict) and item.get("customer_id") == customer_id:
            return item
    raise ValueError(f"customer not found: {customer_id}")


def add_event(customer: dict[str, Any], event: str, note: str = "") -> None:
    events = customer.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError("customer events must be a list")
    events.append({"at": now_iso(), "event": event, "note": note.strip()})


def update_customer(
    data: dict[str, Any],
    *,
    customer_id: str,
    status: str | None = None,
    plan: str | None = None,
    payment_reference: str | None = None,
    contracting_entity: str | None = None,
    monthly_amount: str | None = None,
    currency: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    customer = find_customer(data, customer_id)
    changes: list[str] = []

    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status}")
        if customer.get("status") != status:
            customer["status"] = status
            changes.append(f"status:{status}")

    if plan is not None:
        if plan not in VALID_PLANS:
            raise ValueError(f"invalid plan: {plan}")
        if customer.get("plan") != plan:
            customer["plan"] = plan
            changes.append(f"plan:{plan}")

    if payment_reference is not None:
        customer["payment_reference"] = payment_reference.strip()
        changes.append("payment_reference")

    if contracting_entity is not None:
        customer["contracting_entity"] = contracting_entity.strip()
        changes.append("contracting_entity")

    if monthly_amount is not None:
        customer["monthly_amount"] = normalize_monthly_amount(monthly_amount)
        changes.append("monthly_amount")

    if currency is not None:
        customer["currency"] = normalize_currency(currency)
        changes.append("currency")

    customer["updated_at"] = now_iso()
    add_event(customer, ",".join(changes) if changes else "review", note=note)
    return customer


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update customer lifecycle state.")
    parser.add_argument("--registry-file", type=Path, required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--status", choices=sorted(VALID_STATUSES))
    parser.add_argument("--plan", choices=sorted(VALID_PLANS))
    parser.add_argument("--payment-reference")
    parser.add_argument("--contracting-entity")
    parser.add_argument("--monthly-amount")
    parser.add_argument("--currency")
    parser.add_argument("--note", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data = load_registry(args.registry_file)
        customer = update_customer(
            data,
            customer_id=args.customer_id,
            status=args.status,
            plan=args.plan,
            payment_reference=args.payment_reference,
            contracting_entity=args.contracting_entity,
            monthly_amount=args.monthly_amount,
            currency=args.currency,
            note=args.note,
        )
        save_registry(args.registry_file, data)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2
    print(
        "updated_customer="
        + json.dumps(
            {
                "customer_id": customer.get("customer_id"),
                "status": customer.get("status"),
                "plan": customer.get("plan"),
                "key_fingerprint": customer.get("key_fingerprint"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
