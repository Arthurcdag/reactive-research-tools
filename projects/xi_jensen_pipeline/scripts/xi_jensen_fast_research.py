#!/usr/bin/env python3
"""
xi_jensen_fast_research.py

Research runner built on top of the optimized xi_jensen_fast engine.

Why this exists
---------------
The optimized engine already solved the real bottleneck:
- baseline: ~9 hours on the client's machine
- optimized cold run: ~18 seconds
- warm cache hit: ~40 ms

This wrapper keeps the optimized gamma pipeline and keeps numpy roots as the
default classifier, while adding:
- named presets
- focused targeted runs
- automatic first-defect summary
- optional comparison against an expected CSV
- optional high-precision verification trigger

By design, this does NOT switch the main scan to mp.polyroots. High-precision
polyroots remains a verification tool, not the default production path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

import xi_jensen_fast as F


PRESETS: dict[str, dict] = {
    "client_full": {
        "dps": 100,
        "max_gamma_index": 24,
        "c_values": [0.50, 0.54, 0.56, 0.57, 0.60, 0.70],
        "n_values": list(range(3, 15)),
        "out_csv": "xi_jensen_scan_fast.csv",
        "root_method": "numpy",
        "use_cache": True,
        "use_parallel": False,
    },
    "c070_fast": {
        "dps": 100,
        "max_gamma_index": 24,
        "c_values": [0.70],
        "n_values": list(range(3, 15)),
        "out_csv": "xi_jensen_scan_fast_c070.csv",
        "root_method": "numpy",
        "use_cache": True,
        "use_parallel": False,
    },
    "c060_fast": {
        "dps": 100,
        "max_gamma_index": 24,
        "c_values": [0.60],
        "n_values": list(range(3, 15)),
        "out_csv": "xi_jensen_scan_fast_c060.csv",
        "root_method": "numpy",
        "use_cache": True,
        "use_parallel": False,
    },
    "threshold_band": {
        "dps": 120,
        "max_gamma_index": 30,
        "c_values": [0.56, 0.57, 0.58],
        "n_values": list(range(3, 20)),
        "out_csv": "xi_jensen_scan_fast_threshold_band.csv",
        "root_method": "numpy",
        "use_cache": True,
        "use_parallel": False,
    },
}


def md5_normalized_csv(path: Path) -> str:
    data = path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    return hashlib.md5(data).hexdigest()


def load_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def summarize_rows(rows: list[dict]) -> dict:
    if not rows:
        return {
            "row_count": 0,
            "first_defect": None,
            "defect_rows": 0,
            "endpoint_state_counts": {},
            "defect_location_counts": {},
            "n_range": None,
            "d_range": None,
        }

    norm = []
    for r in rows:
        rr = dict(r)
        rr["n"] = int(rr["n"])
        rr["d"] = int(rr["d"])
        rr["real_root_deficit"] = int(rr["real_root_deficit"])
        norm.append(rr)

    defects = [r for r in norm if r["real_root_deficit"] > 0]
    state_counts = Counter(r["endpoint_state"] for r in norm)
    loc_counts = Counter(r["defect_location"] for r in defects)

    return {
        "row_count": len(norm),
        "first_defect": defects[0] if defects else None,
        "defect_rows": len(defects),
        "endpoint_state_counts": dict(state_counts),
        "defect_location_counts": dict(loc_counts),
        "n_range": [min(r["n"] for r in norm), max(r["n"] for r in norm)],
        "d_range": [min(r["d"] for r in norm), max(r["d"] for r in norm)],
    }


def compare_csvs(path_a: Path, path_b: Path) -> dict:
    rows_a = load_rows(path_a)
    rows_b = load_rows(path_b)
    key_a = {(r["c"], r["n"], r["d"]): r for r in rows_a}
    key_b = {(r["c"], r["n"], r["d"]): r for r in rows_b}

    overlap = sorted(set(key_a) & set(key_b))
    mismatches = []
    for key in overlap:
        a = key_a[key]
        b = key_b[key]
        fields = ["real_root_deficit", "endpoint_state", "defect_location"]
        if any(a[f] != b[f] for f in fields):
            mismatches.append({"key": key, "a": a, "b": b})

    return {
        "rows_a": len(rows_a),
        "rows_b": len(rows_b),
        "overlap": len(overlap),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:10],
        "md5_a": md5_normalized_csv(path_a),
        "md5_b": md5_normalized_csv(path_b),
    }


def write_summary(summary: dict, path: Path) -> None:
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="Research runner for xi_jensen_fast")
    p.add_argument("--preset", choices=sorted(PRESETS.keys()), default="client_full")
    p.add_argument("--compare-to", type=str, help="Optional expected CSV to compare against")
    p.add_argument("--summary-json", type=str, help="Optional output path for JSON summary")
    p.add_argument("--out-csv", type=str, help="Override CSV output name")
    p.add_argument("--use-parallel", action="store_true", help="Enable process parallelism over c-rays")
    p.add_argument("--no-cache", action="store_true", help="Disable gamma cache")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = PRESETS[args.preset].copy()

    if args.out_csv:
        cfg["out_csv"] = args.out_csv
    if args.use_parallel:
        cfg["use_parallel"] = True
    if args.no_cache:
        cfg["use_cache"] = False

    out_csv = Path(cfg["out_csv"])
    print("Running preset:", args.preset)
    print("Config:", cfg)

    gammas, rows_obj = F.run(
        dps=cfg["dps"],
        max_gamma_index=cfg["max_gamma_index"],
        c_values=cfg["c_values"],
        n_values=cfg["n_values"],
        out_csv=out_csv,
        root_method=cfg["root_method"],
        use_cache=cfg["use_cache"],
        use_parallel=cfg["use_parallel"],
        verbose=args.verbose,
    )

    rows = load_rows(out_csv)
    summary = {
        "preset": args.preset,
        "config": cfg,
        "summary": summarize_rows(rows),
        "out_csv": str(out_csv),
        "out_csv_md5_normalized": md5_normalized_csv(out_csv),
    }

    if args.compare_to:
        summary["comparison"] = compare_csvs(out_csv, Path(args.compare_to))

    print("\nSummary:")
    print(json.dumps(summary["summary"], indent=2))
    if "comparison" in summary:
        print("\nComparison:")
        print(json.dumps(summary["comparison"], indent=2))

    if args.summary_json:
        write_summary(summary, Path(args.summary_json))
        print(f"\nWrote summary JSON to {args.summary_json}")


if __name__ == "__main__":
    main()
