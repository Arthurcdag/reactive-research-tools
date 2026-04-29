#!/usr/bin/env python3
"""CLI for the Effective Boolean Argument Filter."""
from __future__ import annotations

import argparse
import json
import sys

from src.effective_boolean_filter import (
    evaluate_argument,
    to_human,
    to_json_dict,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Effective Boolean Argument Filter — a traceable argument-effect filter.",
    )
    parser.add_argument("--claim", required=True, help="The claim under evaluation")
    parser.add_argument("--argument", required=True, help="Argument supporting the claim")
    parser.add_argument("--context", default="", help="Context label (free text)")
    parser.add_argument("--task", default="argument evaluation")
    parser.add_argument(
        "--strictness",
        choices=["low", "medium", "high"],
        default="medium",
    )
    parser.add_argument(
        "--format",
        choices=["json", "human", "both"],
        default="human",
        help="Output format",
    )
    args = parser.parse_args()

    report = evaluate_argument(
        claim=args.claim,
        argument=args.argument,
        context=args.context,
        task=args.task,
        strictness=args.strictness,
    )

    if args.format in ("json", "both"):
        print(json.dumps(to_json_dict(report), indent=2, ensure_ascii=False))
    if args.format == "both":
        print()
    if args.format in ("human", "both"):
        print(to_human(report))

    # exit code: 0 if accept-leaning, 1 if reject-leaning
    return 0 if report.recommendation in ("accept", "accept_with_caveats") else 1


if __name__ == "__main__":
    sys.exit(main())
