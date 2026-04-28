#!/usr/bin/env python3
"""
xi_jensen_compare_runs.py

Compare Xi–Jensen CSV outputs from different scanner variants.

Use cases
---------
1. Summarize a single CSV:
   - first defect row
   - count of defect rows
   - endpoint_like vs bulk_like counts
   - range of n, d

2. Compare two CSVs on overlapping rows keyed by (n, d):
   - agreement in real_root_deficit
   - agreement in endpoint_state
   - agreement in defect_location
   - list mismatches

This is the right script to use after running:
- targeted
- adrian
- fft
- contour_polyroots_scaled

Example
-------
python xi_jensen_compare_runs.py --summary xi_jensen_poly_scaled_c070_validate.csv
python xi_jensen_compare_runs.py --compare xi_jensen_scan_c070.csv xi_jensen_poly_scaled_c070_validate.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from collections import Counter


def load_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_row(r: dict) -> dict:
    out = dict(r)
    if "n" in out:
        out["n"] = int(out["n"])
    if "d" in out:
        out["d"] = int(out["d"])
    if "real_root_deficit" in out:
        out["real_root_deficit"] = int(out["real_root_deficit"])
    return out


def summarize(path: Path) -> None:
    rows = [normalize_row(r) for r in load_rows(path)]
    if not rows:
        print(f"{path.name}: no rows")
        return

    defects = [r for r in rows if r.get("real_root_deficit", 0) > 0]
    loc = Counter(r.get("defect_location", "missing") for r in defects)
    states = Counter(r.get("endpoint_state", "missing") for r in rows)

    print(f"FILE: {path.name}")
    print(f"rows: {len(rows)}")
    print(f"n-range: {rows[0]['n']} .. {rows[-1]['n']}")
    print(f"d-range: {min(r['d'] for r in rows)} .. {max(r['d'] for r in rows)}")
    print(f"defect rows: {len(defects)}")
    print(f"endpoint states: {dict(states)}")
    print(f"defect locations: {dict(loc)}")
    if defects:
        print("first defect row:")
        print(defects[0])
    print()


def compare(path_a: Path, path_b: Path) -> None:
    rows_a = [normalize_row(r) for r in load_rows(path_a)]
    rows_b = [normalize_row(r) for r in load_rows(path_b)]

    map_a = {(r["n"], r["d"]): r for r in rows_a}
    map_b = {(r["n"], r["d"]): r for r in rows_b}

    overlap = sorted(set(map_a) & set(map_b))
    only_a = sorted(set(map_a) - set(map_b))
    only_b = sorted(set(map_b) - set(map_a))

    print(f"A: {path_a.name}")
    print(f"B: {path_b.name}")
    print(f"overlap rows: {len(overlap)}")
    print(f"only in A: {len(only_a)}")
    print(f"only in B: {len(only_b)}")

    deficit_match = 0
    state_match = 0
    loc_match = 0
    mismatches = []

    for key in overlap:
        a = map_a[key]
        b = map_b[key]

        dm = a.get("real_root_deficit") == b.get("real_root_deficit")
        sm = a.get("endpoint_state") == b.get("endpoint_state")
        lm = a.get("defect_location") == b.get("defect_location")

        deficit_match += int(dm)
        state_match += int(sm)
        loc_match += int(lm)

        if not (dm and sm and lm):
            mismatches.append(
                {
                    "key": key,
                    "A_deficit": a.get("real_root_deficit"),
                    "B_deficit": b.get("real_root_deficit"),
                    "A_state": a.get("endpoint_state"),
                    "B_state": b.get("endpoint_state"),
                    "A_loc": a.get("defect_location"),
                    "B_loc": b.get("defect_location"),
                }
            )

    if overlap:
        print(f"deficit agreement: {deficit_match}/{len(overlap)}")
        print(f"state agreement:   {state_match}/{len(overlap)}")
        print(f"location agreement:{loc_match}/{len(overlap)}")

    if mismatches:
        print("\nfirst mismatches:")
        for row in mismatches[:10]:
            print(row)
    else:
        print("\nNo mismatches on overlapping rows.")


def parse_args():
    p = argparse.ArgumentParser(description="Compare Xi–Jensen CSV outputs")
    p.add_argument("--summary", nargs="+", help="Summarize one or more CSV files")
    p.add_argument("--compare", nargs=2, metavar=("CSV_A", "CSV_B"), help="Compare two CSV files")
    return p.parse_args()


def main():
    args = parse_args()

    if args.summary:
        for s in args.summary:
            summarize(Path(s))
        return

    if args.compare:
        compare(Path(args.compare[0]), Path(args.compare[1]))
        return

    raise SystemExit("Use --summary or --compare")


if __name__ == "__main__":
    main()
