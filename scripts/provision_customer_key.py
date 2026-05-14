#!/usr/bin/env python3
"""Provision a Reactive Research Tools customer API key.

The token is shown once. Store it in the hosting provider secret manager or a
password vault, then send the bootstrap URL to the customer over an approved
channel. Do not commit generated tokens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


VALID_PLANS = {"demo", "starter", "pro", "enterprise"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}[a-z0-9]$")


@dataclass(frozen=True)
class ProvisionedKey:
    customer_id: str
    plan: str
    token: str
    fingerprint: str
    env_entry: str
    dashboard_url: str | None


def normalize_base_url(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip().rstrip("/")
    if not stripped:
        return None
    if not (stripped.startswith("https://") or stripped.startswith("http://")):
        raise ValueError("base URL must start with https:// or http://")
    return stripped


def validate_customer_id(value: str) -> str:
    customer_id = value.strip().lower()
    if not SLUG_RE.match(customer_id):
        raise ValueError(
            "customer id must be 3-64 chars: lowercase letters, numbers, '-' or '_'"
        )
    return customer_id


def provision_key(
    *,
    customer_id: str,
    plan: str,
    token_bytes: int = 32,
    base_url: str | None = None,
) -> ProvisionedKey:
    customer_id = validate_customer_id(customer_id)
    if plan not in VALID_PLANS:
        raise ValueError(f"unknown plan {plan!r}; choose one of {sorted(VALID_PLANS)}")
    if token_bytes < 24:
        raise ValueError("token_bytes must be at least 24")

    token = secrets.token_urlsafe(token_bytes)
    fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    env_entry = f"{customer_id}:{plan}:{token}"
    normalized_base_url = normalize_base_url(base_url)
    dashboard_url = (
        f"{normalized_base_url}/?access_key={token}"
        if normalized_base_url is not None
        else None
    )
    return ProvisionedKey(
        customer_id=customer_id,
        plan=plan,
        token=token,
        fingerprint=fingerprint,
        env_entry=env_entry,
        dashboard_url=dashboard_url,
    )


def render_env(provisioned: ProvisionedKey) -> str:
    lines = [
        "# Add this entry to EBF_API_KEYS in the hosting secret manager.",
        "# For multiple customers, separate entries with commas.",
        f"EBF_API_KEYS_APPEND={provisioned.env_entry}",
        "",
        "# Customer handoff:",
        f"key_id={provisioned.customer_id}",
        f"plan={provisioned.plan}",
        f"fingerprint={provisioned.fingerprint}",
    ]
    if provisioned.dashboard_url:
        lines.append(f"dashboard_url={provisioned.dashboard_url}")
    return "\n".join(lines) + "\n"


def append_to_file(path: Path, provisioned: ProvisionedKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(render_env(provisioned))
        file.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision a customer API key.")
    parser.add_argument("--customer-id", required=True, help="Stable customer slug")
    parser.add_argument("--plan", choices=sorted(VALID_PLANS), default="starter")
    parser.add_argument("--base-url", help="Dashboard/API base URL for bootstrap link")
    parser.add_argument("--token-bytes", type=int, default=32)
    parser.add_argument(
        "--format",
        choices=["env", "json"],
        default="env",
        help="Output format",
    )
    parser.add_argument(
        "--append-file",
        type=Path,
        help="Optional local secret file to append the generated entry to",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        provisioned = provision_key(
            customer_id=args.customer_id,
            plan=args.plan,
            token_bytes=args.token_bytes,
            base_url=args.base_url,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.append_file:
        append_to_file(args.append_file, provisioned)

    if args.format == "json":
        print(json.dumps(asdict(provisioned), indent=2))
    else:
        print(render_env(provisioned), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
