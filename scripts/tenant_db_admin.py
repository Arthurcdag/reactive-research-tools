#!/usr/bin/env python3
"""Admin CLI for the SQLite tenant database.

Drives the same :class:`TenantDatabase` the auth path and the payment
webhook use. Token plaintext from ``keys provision`` is printed to
stdout exactly once and is never persisted in the DB — capture it from
the script's output and hand it to ``EBF_API_KEYS`` (env-var path) or
to the customer directly.

Common operations::

    # one-time backfill from the existing JSON registry
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        sync-from-registry --registry /data/customer_registry.json

    # tenants
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite tenants list
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        tenants create --tenant-id customer-a --plan starter
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        tenants set-plan --tenant-id customer-a --plan pro
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        tenants set-status --tenant-id customer-a --status suspended

    # API keys
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        keys provision --tenant-id customer-a
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        keys list --tenant-id customer-a
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite \
        keys revoke --key-id customer-a-12345678

    # reports
    python scripts/tenant_db_admin.py --db /data/tenant.sqlite reports reap

The CLI is intentionally thin: every subcommand maps to one
:class:`TenantDatabase` call and prints JSON on stdout so it can be
piped into ``jq`` or wrapped by other tooling.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the package importable when running directly out of the repo.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "projects" / "effective_boolean_filter" / "src"))

from effective_boolean_filter.tenant_db import (  # noqa: E402
    TenantDatabase,
    TenantDBError,
    sync_tenants_from_registry,
)


def _print_json(obj: object) -> None:
    print(json.dumps(obj, sort_keys=True, indent=2))


def cmd_tenants_list(db: TenantDatabase, args: argparse.Namespace) -> int:
    _print_json([t.to_dict() for t in db.list_tenants()])
    return 0


def cmd_tenants_create(db: TenantDatabase, args: argparse.Namespace) -> int:
    tenant = db.upsert_tenant(
        args.tenant_id,
        plan=args.plan,
        status=args.status,
        payment_reference=args.payment_reference,
        contracting_entity=args.contracting_entity,
        monthly_amount=args.monthly_amount,
        currency=args.currency,
    )
    _print_json(tenant.to_dict())
    return 0


def cmd_tenants_set_plan(db: TenantDatabase, args: argparse.Namespace) -> int:
    _print_json(db.set_tenant_plan(args.tenant_id, args.plan).to_dict())
    return 0


def cmd_tenants_set_status(db: TenantDatabase, args: argparse.Namespace) -> int:
    _print_json(db.set_tenant_status(args.tenant_id, args.status).to_dict())
    return 0


def cmd_keys_provision(db: TenantDatabase, args: argparse.Namespace) -> int:
    provisioned = db.provision_api_key(
        tenant_id=args.tenant_id,
        key_id=args.key_id,
        plan=args.plan,
        token_bytes=args.token_bytes,
    )
    _print_json(
        {
            "key_id": provisioned.key_id,
            "tenant_id": provisioned.tenant_id,
            "plan": provisioned.plan,
            "token": provisioned.token,  # SHOWN ONCE
            "token_display_fingerprint": provisioned.token_display_fingerprint,
            "created_at": provisioned.created_at,
            "note": "Capture the token now — the DB never sees it again.",
        }
    )
    return 0


def cmd_keys_list(db: TenantDatabase, args: argparse.Namespace) -> int:
    keys = db.list_api_keys(args.tenant_id)
    _print_json([k.to_dict() for k in keys])
    return 0


def cmd_keys_revoke(db: TenantDatabase, args: argparse.Namespace) -> int:
    _print_json(db.revoke_api_key(args.key_id).to_dict())
    return 0


def cmd_reports_reap(db: TenantDatabase, args: argparse.Namespace) -> int:
    deleted = db.delete_expired_reports()
    _print_json({"deleted": deleted})
    return 0


def cmd_sync_from_registry(db: TenantDatabase, args: argparse.Namespace) -> int:
    counts = sync_tenants_from_registry(db, args.registry)
    _print_json(counts)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tenant DB admin CLI")
    parser.add_argument(
        "--db",
        required=True,
        help="SQLite path (e.g. /data/tenant.sqlite). ':memory:' is allowed for testing.",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    # tenants
    tenants = sub.add_parser("tenants", help="Tenant operations")
    tenants_sub = tenants.add_subparsers(dest="action", required=True)

    tenants_sub.add_parser("list", help="List all tenants").set_defaults(
        func=cmd_tenants_list
    )

    create = tenants_sub.add_parser("create", help="Create or update a tenant")
    create.add_argument("--tenant-id", required=True)
    create.add_argument("--plan", required=True, choices=sorted({"demo", "starter", "pro", "enterprise"}))
    create.add_argument("--status", default="active", choices=sorted({"active", "suspended", "canceled"}))
    create.add_argument("--payment-reference", default="")
    create.add_argument("--contracting-entity", default="")
    create.add_argument("--monthly-amount", default="")
    create.add_argument("--currency", default="")
    create.set_defaults(func=cmd_tenants_create)

    set_plan = tenants_sub.add_parser("set-plan", help="Change a tenant's plan")
    set_plan.add_argument("--tenant-id", required=True)
    set_plan.add_argument("--plan", required=True, choices=sorted({"demo", "starter", "pro", "enterprise"}))
    set_plan.set_defaults(func=cmd_tenants_set_plan)

    set_status = tenants_sub.add_parser("set-status", help="Change a tenant's status")
    set_status.add_argument("--tenant-id", required=True)
    set_status.add_argument("--status", required=True, choices=sorted({"active", "suspended", "canceled"}))
    set_status.set_defaults(func=cmd_tenants_set_status)

    # keys
    keys = sub.add_parser("keys", help="API key operations")
    keys_sub = keys.add_subparsers(dest="action", required=True)

    provision = keys_sub.add_parser("provision", help="Mint an API key (shown once)")
    provision.add_argument("--tenant-id", required=True)
    provision.add_argument("--key-id", default=None, help="Optional custom key id")
    provision.add_argument(
        "--plan",
        default=None,
        choices=sorted({"demo", "starter", "pro", "enterprise"}),
        help="Plan override (defaults to the tenant's plan)",
    )
    provision.add_argument("--token-bytes", type=int, default=32)
    provision.set_defaults(func=cmd_keys_provision)

    list_keys = keys_sub.add_parser("list", help="List API keys")
    list_keys.add_argument("--tenant-id", default=None)
    list_keys.set_defaults(func=cmd_keys_list)

    revoke = keys_sub.add_parser("revoke", help="Revoke an API key")
    revoke.add_argument("--key-id", required=True)
    revoke.set_defaults(func=cmd_keys_revoke)

    # reports
    reports = sub.add_parser("reports", help="Report operations")
    reports_sub = reports.add_subparsers(dest="action", required=True)
    reports_sub.add_parser("reap", help="Delete reports past their expires_at").set_defaults(
        func=cmd_reports_reap
    )

    # sync
    sync = sub.add_parser(
        "sync-from-registry",
        help="Backfill tenants from a rtt_customer_registry_v1 JSON file",
    )
    sync.add_argument("--registry", required=True, help="Path to customer_registry.json")
    sync.set_defaults(func=cmd_sync_from_registry)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db = TenantDatabase(args.db)
    try:
        return int(args.func(db, args))
    except TenantDBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
