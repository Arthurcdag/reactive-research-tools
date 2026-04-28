#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import xi_jensen_fast as F
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


def read_completed_cs(frontier_csv: Path) -> set[float]:
    if not frontier_csv.exists():
        return set()
    done = set()
    with frontier_csv.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            done.add(float(row["c"]))
    return done


def ensure_rows_csv(rows_csv: Path) -> None:
    if rows_csv.exists():
        return
    fields = list(EXP.asdict(EXP.DetailedRow(
        c=0.0, n=0, d=0, c_nd=0.0,
        real_root_deficit=0, endpoint_state="0", defect_location="none",
        min_nonreal_abs_imag=0.0, sensitive=False, verified=False,
        verified_match=None, hi_real_root_deficit=None,
        hi_endpoint_state=None, hi_defect_location=None,
    )).keys())
    with rows_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()


def append_rows(rows_csv: Path, rows) -> None:
    if not rows:
        return
    fields = list(EXP.asdict(rows[0]).keys())
    with rows_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        for row in rows:
            w.writerow(EXP.asdict(row))


def ensure_frontier_csv(frontier_csv: Path) -> None:
    if frontier_csv.exists():
        return
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
    with frontier_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()


def append_frontier_row(frontier_csv: Path, row: dict) -> None:
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
    with frontier_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writerow(row)


def write_summary(summary_json: Path, *, config: dict, frontier_rows: list[dict], rows_csv: Path, frontier_csv: Path) -> None:
    summary = {
        "config": config,
        "frontier_rows": frontier_rows,
        "full_csv": str(rows_csv),
        "frontier_csv": str(frontier_csv),
        "full_csv_md5_normalized": EXP.md5_normalized_csv(rows_csv) if rows_csv.exists() else None,
        "frontier_csv_md5_normalized": EXP.md5_normalized_csv(frontier_csv) if frontier_csv.exists() else None,
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="Live/resumable threshold-frontier explorer for xi_jensen_fast")
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
    p.add_argument("--prefix", type=str, default="xi_jensen_frontier_live")
    p.add_argument("--verbose-gammas", action="store_true", help="Show progress while computing gamma coefficients")
    p.add_argument("--force-recompute-gammas", action="store_true", help="Ignore gamma cache and recompute")
    return p.parse_args()


def main():
    args = parse_args()

    c_values = frange(args.c_start, args.c_stop, args.c_step)
    n_values = list(range(args.n_start, args.n_stop + 1))

    max_gamma_index = args.max_gamma_index
    if max_gamma_index is None:
        max_gamma_index = EXP.auto_max_gamma_index(c_values, n_values)

    rows_csv = Path(f"{args.prefix}_rows.csv")
    frontier_csv = Path(f"{args.prefix}_frontier.csv")
    summary_json = Path(f"{args.prefix}_summary.json")

    config = {
        "c_values": c_values,
        "n_values": n_values,
        "dps": args.dps,
        "max_gamma_index": max_gamma_index,
        "verify_sensitive": args.verify_sensitive,
        "verify_factor": args.verify_factor,
        "hi_dps": args.hi_dps,
    }

    print("c-values:", c_values, flush=True)
    print("n-range:", (args.n_start, args.n_stop), flush=True)
    print("dps:", args.dps, flush=True)
    print("max_gamma_index:", max_gamma_index, flush=True)

    gammas = F.xi_gammas_cached(
        max_index=max_gamma_index,
        dps=args.dps,
        cache_dir=".gamma_cache",
        force=args.force_recompute_gammas,
        verbose=args.verbose_gammas,
    )

    ensure_rows_csv(rows_csv)
    ensure_frontier_csv(frontier_csv)

    completed_cs = read_completed_cs(frontier_csv)
    frontier_rows = []
    if frontier_csv.exists():
        with frontier_csv.open("r", newline="", encoding="utf-8") as f:
            frontier_rows = list(csv.DictReader(f))

    for i, c in enumerate(c_values, start=1):
        if c in completed_cs:
            print(f"[{i}/{len(c_values)}] c={c}: already completed, skipping", flush=True)
            continue

        print(f"[{i}/{len(c_values)}] scanning c={c} ...", flush=True)
        rows = EXP.scan_ray_detailed(
            gammas,
            c,
            n_values,
            verify_sensitive=args.verify_sensitive,
            verify_factor=args.verify_factor,
            hi_dps=args.hi_dps,
        )
        append_rows(rows_csv, rows)

        fd = first_defect_row(rows)
        frontier_row = {
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
        }
        append_frontier_row(frontier_csv, frontier_row)
        frontier_rows.append(frontier_row)
        write_summary(summary_json, config=config, frontier_rows=frontier_rows, rows_csv=rows_csv, frontier_csv=frontier_csv)

        print(
            f"[{i}/{len(c_values)}] done c={c}: rows={frontier_row['row_count']}, "
            f"defects={frontier_row['defect_rows']}, "
            f"first_defect_n={frontier_row['first_defect_n']}",
            flush=True
        )

    print(f"Wrote {rows_csv}", flush=True)
    print(f"Wrote {frontier_csv}", flush=True)
    print(f"Wrote {summary_json}", flush=True)


if __name__ == "__main__":
    main()
