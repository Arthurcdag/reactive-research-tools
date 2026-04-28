#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from src.effective_boolean_filter.engine import evaluate_argument


def main() -> None:
    parser = argparse.ArgumentParser(description="Effective Boolean Argument Filter MVP")
    parser.add_argument("--claim", required=True)
    parser.add_argument("--argument", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--task", default="argument evaluation")
    parser.add_argument("--strictness", choices=["low", "medium", "high"], default="medium")
    args = parser.parse_args()

    report = evaluate_argument(
        claim=args.claim,
        argument=args.argument,
        context=args.context,
        task=args.task,
        strictness=args.strictness,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
