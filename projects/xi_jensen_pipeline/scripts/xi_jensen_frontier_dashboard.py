#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import time
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


def threshold_constant() -> float:
    return 1.0 / math.sqrt(math.pi)


def alpha_of_c(c: float) -> float | None:
    if c <= threshold_constant():
        return None
    kappa = math.log(c * math.sqrt(math.pi))
    return (4.0 * c / 3.0) * (kappa ** 1.5)


def n0_scale(c: float) -> float | None:
    a = alpha_of_c(c)
    if a is None or a <= 0:
        return None
    return (a ** (-2.0 / 3.0)) * (math.log(1.0 / a) ** (4.0 / 3.0))


def Nc_scale(c: float) -> float | None:
    a = alpha_of_c(c)
    if a is None or a <= 0:
        return None
    return (a ** (-2.0)) * (math.log(1.0 / a) ** 4.0)


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
        csv.DictWriter(f, fieldnames=fields).writeheader()


def append_rows(rows_csv: Path, rows) -> None:
    if not rows:
        return
    fields = list(EXP.asdict(rows[0]).keys())
    with rows_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        for row in rows:
            w.writerow(EXP.asdict(row))


FRONTIER_FIELDS = [
    "c",
    "c_minus_threshold",
    "alpha",
    "n0_pred",
    "Nc_pred",
    "row_count",
    "defect_rows",
    "first_defect_n",
    "first_defect_d",
    "first_defect_deficit",
    "first_defect_location",
    "sensitive_rows",
    "verified_rows",
    "verification_mismatches",
    "seconds",
]


def ensure_frontier_csv(frontier_csv: Path) -> None:
    if frontier_csv.exists():
        return
    with frontier_csv.open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FRONTIER_FIELDS).writeheader()


def append_frontier_row(frontier_csv: Path, row: dict) -> None:
    with frontier_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FRONTIER_FIELDS)
        w.writerow(row)


def read_frontier_rows(frontier_csv: Path) -> list[dict]:
    if not frontier_csv.exists():
        return []
    with frontier_csv.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seconds_fmt(x: float) -> str:
    if x < 60:
        return f"{x:.1f}s"
    if x < 3600:
        return f"{x/60:.1f}m"
    return f"{x/3600:.2f}h"


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


def write_markdown_report(report_md: Path, *, config: dict, frontier_rows: list[dict], rows_csv: Path, frontier_csv: Path, summary_json: Path) -> None:
    lines = []
    lines.append("# Xi–Jensen threshold frontier dashboard")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for k, v in config.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(f"- rows CSV: `{rows_csv}`")
    lines.append(f"- frontier CSV: `{frontier_csv}`")
    lines.append(f"- summary JSON: `{summary_json}`")
    lines.append("")
    lines.append("## Frontier")
    lines.append("")
    lines.append("| c | c-threshold | alpha | n0 pred | Nc pred | rows | defects | first n | first d | loc | sensitive | verified | mismatches | seconds |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|")
    for r in frontier_rows:
        def val(name):
            x = r.get(name, "")
            return "" if x in (None, "None") else x
        lines.append(
            f"| {val('c')} | {val('c_minus_threshold')} | {val('alpha')} | {val('n0_pred')} | {val('Nc_pred')} | "
            f"{val('row_count')} | {val('defect_rows')} | {val('first_defect_n')} | {val('first_defect_d')} | "
            f"{val('first_defect_location')} | {val('sensitive_rows')} | {val('verified_rows')} | "
            f"{val('verification_mismatches')} | {val('seconds')} |"
        )
    report_md.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="Dashboard-style threshold-frontier explorer for xi_jensen_fast")
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
    p.add_argument("--prefix", type=str, default="xi_jensen_dashboard")
    p.add_argument("--verbose-gammas", action="store_true")
    p.add_argument("--force-recompute-gammas", action="store_true")
    p.add_argument("--stop-after-c", type=float, default=None, help="Optional debugging stop after this c value")
    return p.parse_args()


def main():
    args = parse_args()
    t_total0 = time.perf_counter()

    c_values = frange(args.c_start, args.c_stop, args.c_step)
    n_values = list(range(args.n_start, args.n_stop + 1))

    max_gamma_index = args.max_gamma_index
    if max_gamma_index is None:
        max_gamma_index = EXP.auto_max_gamma_index(c_values, n_values)

    rows_csv = Path(f"{args.prefix}_rows.csv")
    frontier_csv = Path(f"{args.prefix}_frontier.csv")
    summary_json = Path(f"{args.prefix}_summary.json")
    report_md = Path(f"{args.prefix}_report.md")

    config = {
        "c_values": c_values,
        "n_values": n_values,
        "dps": args.dps,
        "max_gamma_index": max_gamma_index,
        "verify_sensitive": args.verify_sensitive,
        "verify_factor": args.verify_factor,
        "hi_dps": args.hi_dps,
        "threshold_constant": threshold_constant(),
    }

    print("=== Xi–Jensen frontier dashboard ===", flush=True)
    print("c-values:", c_values, flush=True)
    print("n-range:", (args.n_start, args.n_stop), flush=True)
    print("dps:", args.dps, flush=True)
    print("max_gamma_index:", max_gamma_index, flush=True)
    print("verify_sensitive:", args.verify_sensitive, flush=True)

    print("\n[phase] gamma table load/compute", flush=True)
    t_gamma0 = time.perf_counter()
    gammas = F.xi_gammas_cached(
        max_index=max_gamma_index,
        dps=args.dps,
        cache_dir=".gamma_cache",
        force=args.force_recompute_gammas,
        verbose=args.verbose_gammas,
    )
    gamma_seconds = time.perf_counter() - t_gamma0
    print(f"[phase] gamma table ready in {seconds_fmt(gamma_seconds)}", flush=True)

    ensure_rows_csv(rows_csv)
    ensure_frontier_csv(frontier_csv)

    completed_cs = read_completed_cs(frontier_csv)
    frontier_rows = read_frontier_rows(frontier_csv)

    remaining = [c for c in c_values if c not in completed_cs]
    completed_count = len(c_values) - len(remaining)
    scan_times = []

    for i, c in enumerate(c_values, start=1):
        if c in completed_cs:
            print(f"[{i}/{len(c_values)}] c={c}: already completed, skipping", flush=True)
            continue

        if scan_times:
            avg = sum(scan_times) / len(scan_times)
            eta = avg * (len(remaining) - len(scan_times))
            print(f"[eta] avg per c={seconds_fmt(avg)}, remaining estimate={seconds_fmt(eta)}", flush=True)

        print(f"[{i}/{len(c_values)}] scanning c={c} ...", flush=True)
        t_c0 = time.perf_counter()
        rows = EXP.scan_ray_detailed(
            gammas,
            c,
            n_values,
            verify_sensitive=args.verify_sensitive,
            verify_factor=args.verify_factor,
            hi_dps=args.hi_dps,
        )
        seconds = time.perf_counter() - t_c0
        scan_times.append(seconds)

        append_rows(rows_csv, rows)

        fd = first_defect_row(rows)
        a = alpha_of_c(c)
        n0 = n0_scale(c)
        Nc = Nc_scale(c)

        frontier_row = {
            "c": c,
            "c_minus_threshold": c - threshold_constant(),
            "alpha": None if a is None else a,
            "n0_pred": None if n0 is None else n0,
            "Nc_pred": None if Nc is None else Nc,
            "row_count": len(rows),
            "defect_rows": sum(r.real_root_deficit > 0 for r in rows),
            "first_defect_n": None if fd is None else fd.n,
            "first_defect_d": None if fd is None else fd.d,
            "first_defect_deficit": None if fd is None else fd.real_root_deficit,
            "first_defect_location": None if fd is None else fd.defect_location,
            "sensitive_rows": sum(r.sensitive for r in rows),
            "verified_rows": sum(r.verified for r in rows),
            "verification_mismatches": sum(r.verified and (r.verified_match is False) for r in rows),
            "seconds": seconds,
        }
        append_frontier_row(frontier_csv, frontier_row)
        frontier_rows.append({k: str(v) if v is not None else "" for k, v in frontier_row.items()})

        write_summary(summary_json, config=config, frontier_rows=frontier_rows, rows_csv=rows_csv, frontier_csv=frontier_csv)
        write_markdown_report(report_md, config=config, frontier_rows=frontier_rows, rows_csv=rows_csv, frontier_csv=frontier_csv, summary_json=summary_json)

        print(
            f"[{i}/{len(c_values)}] done c={c}: rows={frontier_row['row_count']}, "
            f"defects={frontier_row['defect_rows']}, "
            f"first_defect_n={frontier_row['first_defect_n']}, "
            f"time={seconds_fmt(seconds)}",
            flush=True,
        )

        if args.stop_after_c is not None and abs(c - args.stop_after_c) < 1e-15:
            print(f"[stop] requested stop after c={c}", flush=True)
            break

    total_seconds = time.perf_counter() - t_total0
    print("\n=== done ===", flush=True)
    print(f"total time: {seconds_fmt(total_seconds)}", flush=True)
    print(f"Wrote {rows_csv}", flush=True)
    print(f"Wrote {frontier_csv}", flush=True)
    print(f"Wrote {summary_json}", flush=True)
    print(f"Wrote {report_md}", flush=True)


if __name__ == "__main__":
    main()
