#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import mpmath as mp

import xi_jensen_fast as F


def parse_bool(x: str) -> bool:
    return str(x).strip().lower() in {"1", "true", "yes", "y"}


def load_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select_rows(rows: list[dict], *, only_sensitive: bool, max_d: int | None, min_n: int | None, max_n: int | None, limit: int | None) -> list[dict]:
    selected = []
    for r in rows:
        d = int(r["d"])
        n = int(r["n"])

        if only_sensitive and not parse_bool(r.get("sensitive", "false")):
            continue
        if max_d is not None and d > max_d:
            continue
        if min_n is not None and n < min_n:
            continue
        if max_n is not None and n > max_n:
            continue

        selected.append(r)
        if limit is not None and len(selected) >= limit:
            break

    return selected


def classify_roots(n: int, d: int, roots, tol: float):
    real_count = F.count_real_roots(roots, tol=tol)
    return {
        "hi_real_root_deficit": int(d - real_count),
        "hi_endpoint_state": F.endpoint_state_proxy(roots, tol=tol),
        "hi_defect_location": F.defect_location_proxy(roots, tol=tol),
    }


def verify_one(row: dict, gammas, *, tol: float, maxsteps: int, extraprec: int) -> dict:
    c = float(row["c"])
    n = int(row["n"])
    d = int(row["d"])

    coeffs = F.jensen_coeffs(gammas, n, d)
    roots = F.roots_mpmath(coeffs, maxsteps=maxsteps, cleanup=True, extraprec=extraprec)
    hi = classify_roots(n, d, roots, tol)

    lo_deficit = int(row["real_root_deficit"])
    lo_state = row["endpoint_state"]
    lo_loc = row["defect_location"]

    match = (
        lo_deficit == hi["hi_real_root_deficit"]
        and lo_state == hi["hi_endpoint_state"]
        and lo_loc == hi["hi_defect_location"]
    )

    return {
        "c": c,
        "n": n,
        "d": d,
        "lo_real_root_deficit": lo_deficit,
        "lo_endpoint_state": lo_state,
        "lo_defect_location": lo_loc,
        **hi,
        "verified_match": match,
        "status": "ok",
        "error": "",
    }


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def parse_args():
    p = argparse.ArgumentParser(description="Post-hoc high-precision verifier for Xi-Jensen CSV rows")
    p.add_argument("--rows", required=True, help="Rows CSV from dashboard/frontier run")
    p.add_argument("--out", default="xi_jensen_verify_queue_results.csv")
    p.add_argument("--summary-json", default="xi_jensen_verify_queue_summary.json")
    p.add_argument("--dps", type=int, default=150)
    p.add_argument("--max-gamma-index", type=int, default=None, help="Defaults to max(n+d) over selected rows")
    p.add_argument("--tol", type=float, default=1e-8)
    p.add_argument("--maxsteps", type=int, default=300)
    p.add_argument("--extraprec", type=int, default=80)
    p.add_argument("--only-sensitive", action="store_true")
    p.add_argument("--max-d", type=int, default=60)
    p.add_argument("--min-n", type=int)
    p.add_argument("--max-n", type=int)
    p.add_argument("--limit", type=int)
    return p.parse_args()


def main():
    args = parse_args()

    rows_path = Path(args.rows)
    rows = load_rows(rows_path)
    selected = select_rows(
        rows,
        only_sensitive=args.only_sensitive,
        max_d=args.max_d,
        min_n=args.min_n,
        max_n=args.max_n,
        limit=args.limit,
    )

    if not selected:
        print("No rows selected.")
        return

    max_gamma_index = args.max_gamma_index
    if max_gamma_index is None:
        max_gamma_index = max(int(r["n"]) + int(r["d"]) for r in selected) + 4

    print(f"Rows loaded: {len(rows)}")
    print(f"Rows selected: {len(selected)}")
    print(f"dps: {args.dps}")
    print(f"max_gamma_index: {max_gamma_index}")
    print(f"max_d gate: {args.max_d}")

    mp.mp.dps = args.dps
    gammas = F.xi_gammas_cached(max_gamma_index, dps=args.dps, cache_dir=".gamma_cache", verbose=True)

    results = []
    t0 = time.perf_counter()
    for i, row in enumerate(selected, start=1):
        c = row["c"]
        n = row["n"]
        d = row["d"]
        print(f"[{i}/{len(selected)}] verifying c={c}, n={n}, d={d} ...", flush=True)
        rt0 = time.perf_counter()
        try:
            result = verify_one(row, gammas, tol=args.tol, maxsteps=args.maxsteps, extraprec=args.extraprec)
        except Exception as e:
            result = {
                "c": float(c),
                "n": int(n),
                "d": int(d),
                "lo_real_root_deficit": int(row["real_root_deficit"]),
                "lo_endpoint_state": row["endpoint_state"],
                "lo_defect_location": row["defect_location"],
                "hi_real_root_deficit": "",
                "hi_endpoint_state": "",
                "hi_defect_location": "",
                "verified_match": "",
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            }
        result["seconds"] = time.perf_counter() - rt0
        results.append(result)

    elapsed = time.perf_counter() - t0
    out = Path(args.out)
    summary_json = Path(args.summary_json)

    write_csv(results, out)

    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] == "failed"]
    mismatches = [r for r in ok if r["verified_match"] is False]

    summary = {
        "input_rows": str(rows_path),
        "out": str(out),
        "rows_loaded": len(rows),
        "rows_selected": len(selected),
        "ok": len(ok),
        "failed": len(failed),
        "mismatches": len(mismatches),
        "elapsed_seconds": elapsed,
        "config": {
            "dps": args.dps,
            "max_gamma_index": max_gamma_index,
            "tol": args.tol,
            "maxsteps": args.maxsteps,
            "extraprec": args.extraprec,
            "only_sensitive": args.only_sensitive,
            "max_d": args.max_d,
            "min_n": args.min_n,
            "max_n": args.max_n,
            "limit": args.limit,
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nDone in {elapsed:.2f}s")
    print(f"ok={len(ok)}, failed={len(failed)}, mismatches={len(mismatches)}")
    print(f"Wrote {out}")
    print(f"Wrote {summary_json}")


if __name__ == "__main__":
    main()
