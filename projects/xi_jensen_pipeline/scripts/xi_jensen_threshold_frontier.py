#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import xi_jensen_fast_experiments as EXP


def frange(start: float, stop: float, step: float) -> list[float]:
    vals = []
    x = start
    while x <= stop + 1e-15:
        vals.append(round(x, 12))
        x += step
    return vals


def first_defect_row(rows):
    for r in rows:
        if r.real_root_deficit > 0:
            return r
    return None


def write_frontier_csv(frontier_rows, path: Path) -> None:
    fields = [
        "c",
        "row_count",
        "defect_rows",
        "first_defect_n",
        "first_defect_d",
        "first_defect_deficit",
        "first_defect_location",
        "sensitive_rows",
        "verified_rows",
        "verification_mismatches",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(frontier_rows)


def parse_args():
    p = argparse.ArgumentParser(description="Threshold-frontier explorer for xi_jensen_fast")
    p.add_argument("--c-start", type=float, default=0.54)
    p.add_argument("--c-stop", type=float, default=0.60)
    p.add_argument("--c-step", type=float, default=0.01)
    p.add_argument("--n-start", type=int, default=3)
    p.add_argument("--n-stop", type=int, default=40)
    p.add_argument("--dps", type=int, default=110)
    p.add_argument("--max-gamma-index", type=int, default=None)
    p.add_argument("--verify-sensitive", action="store_true")
    p.add_argument("--verify-factor", type=float, default=50.0)
    p.add_argument("--hi-dps", type=int, default=150)
    p.add_argument("--prefix", type=str, default="xi_jensen_frontier")
    return p.parse_args()


def main():
    args = parse_args()

    c_values = frange(args.c_start, args.c_stop, args.c_step)
    n_values = list(range(args.n_start, args.n_stop + 1))

    max_gamma_index = args.max_gamma_index
    if max_gamma_index is None:
        max_gamma_index = EXP.auto_max_gamma_index(c_values, n_values)

    print("c-values:", c_values)
    print("n-range:", (args.n_start, args.n_stop))
    print("dps:", args.dps)
    print("max_gamma_index:", max_gamma_index)

    gammas = EXP.F.xi_gammas_cached(
        max_index=max_gamma_index,
        dps=args.dps,
        cache_dir=".gamma_cache",
        verbose=False,
    )

    all_rows = []
    frontier_rows = []

    for c in c_values:
        rows = EXP.scan_ray_detailed(
            gammas,
            c,
            n_values,
            verify_sensitive=args.verify_sensitive,
            verify_factor=args.verify_factor,
            hi_dps=args.hi_dps,
        )
        all_rows.extend(rows)

        fd = first_defect_row(rows)
        frontier_rows.append({
            "c": c,
            "row_count": len(rows),
            "defect_rows": sum(r.real_root_deficit > 0 for r in rows),
            "first_defect_n": None if fd is None else fd.n,
            "first_defect_d": None if fd is None else fd.d,
            "first_defect_deficit": None if fd is None else fd.real_root_deficit,
            "first_defect_location": None if fd is None else fd.defect_location,
            "sensitive_rows": sum(r.sensitive for r in rows),
            "verified_rows": sum(r.verified for r in rows),
            "verification_mismatches": sum(r.verified and (r.verified_match is False) for r in rows),
        })

    full_csv = Path(f"{args.prefix}_rows.csv")
    frontier_csv = Path(f"{args.prefix}_frontier.csv")
    summary_json = Path(f"{args.prefix}_summary.json")

    if all_rows:
        EXP.write_detailed_csv(all_rows, full_csv)
    write_frontier_csv(frontier_rows, frontier_csv)

    summary = {
        "config": {
            "c_values": c_values,
            "n_values": n_values,
            "dps": args.dps,
            "max_gamma_index": max_gamma_index,
            "verify_sensitive": args.verify_sensitive,
            "verify_factor": args.verify_factor,
            "hi_dps": args.hi_dps,
        },
        "frontier_rows": frontier_rows,
        "full_csv": str(full_csv),
        "frontier_csv": str(frontier_csv),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {full_csv}")
    print(f"Wrote {frontier_csv}")
    print(f"Wrote {summary_json}")


if __name__ == "__main__":
    main()
