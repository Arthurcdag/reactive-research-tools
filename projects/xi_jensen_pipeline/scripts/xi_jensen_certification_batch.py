#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import mpmath as mp

import xi_jensen_fast as F
import xi_jensen_deepcheck as D


def load_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def row_key(r: dict) -> tuple[str, str, str]:
    return (str(r["c"]), str(r["n"]), str(r["d"]))


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def append_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    exists = path.exists() and path.stat().st_size > 0
    fields = list(rows[0].keys())
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerows(rows)


def parse_c_list(s: str | None) -> set[str] | None:
    if not s:
        return None
    return {x.strip() for x in s.split(",") if x.strip()}


def select_rows(
    rows: list[dict],
    *,
    status: str,
    c_values: set[str] | None,
    min_n: int | None,
    max_n: int | None,
    min_d: int | None,
    max_d: int | None,
    limit: int | None,
    skip_keys: set[tuple[str, str, str]],
) -> list[dict]:
    out = []
    for r in rows:
        if row_key(r) in skip_keys:
            continue

        c = str(r["c"])
        n = int(float(r["n"]))
        d = int(float(r["d"]))

        if status != "any" and r.get("certified_status", "") != status:
            continue
        if c_values is not None and c not in c_values:
            continue
        if min_n is not None and n < min_n:
            continue
        if max_n is not None and n > max_n:
            continue
        if min_d is not None and d < min_d:
            continue
        if max_d is not None and d > max_d:
            continue

        out.append(r)
        if limit is not None and len(out) >= limit:
            break

    return out


def to_deepcheck_target(row: dict) -> dict:
    return {
        "deepcheck_source": "certification_batch",
        "c": row["c"],
        "n": row["n"],
        "d": row["d"],
        "lo_real_root_deficit": row.get("certified_real_root_deficit", row.get("real_root_deficit", "")),
        "lo_endpoint_state": row.get("certified_endpoint_state", row.get("endpoint_state", "")),
        "lo_defect_location": row.get("certified_defect_location", row.get("defect_location", "")),
        "hi_real_root_deficit": row.get("deep_real_root_deficit", ""),
        "hi_endpoint_state": row.get("deep_endpoint_state", ""),
        "hi_defect_location": row.get("deep_defect_location", ""),
    }


def failed_result(target: dict, error: Exception, seconds: float) -> dict:
    return {
        "source": target.get("deepcheck_source", ""),
        "c": float(target["c"]),
        "n": int(float(target["n"])),
        "d": int(float(target["d"])),
        "lo_real_root_deficit": target.get("lo_real_root_deficit", ""),
        "lo_endpoint_state": target.get("lo_endpoint_state", ""),
        "lo_defect_location": target.get("lo_defect_location", ""),
        "old_hi_real_root_deficit": target.get("hi_real_root_deficit", ""),
        "old_hi_endpoint_state": target.get("hi_endpoint_state", ""),
        "old_hi_defect_location": target.get("hi_defect_location", ""),
        "deep_real_root_deficit": "",
        "deep_endpoint_state": "",
        "deep_defect_location": "",
        "match_lo": "",
        "match_old_hi": "",
        "method": "",
        "max_rel_residual": "",
        "median_rel_residual": "",
        "status": "failed",
        "error": f"{type(error).__name__}: {error}",
        "seconds": seconds,
    }


def parse_args():
    p = argparse.ArgumentParser(description="Deepcheck unverified certified rows in batches")
    p.add_argument("--rows", default="xi_jensen_certified_rows.csv")
    p.add_argument("--out", default="xi_jensen_certification_batch_results.csv")
    p.add_argument("--summary-json", default="xi_jensen_certification_batch_summary.json")
    p.add_argument("--status", default="unverified", choices=["unverified", "deepcheck_ok", "any"])
    p.add_argument("--c-values", default=None)
    p.add_argument("--min-n", type=int)
    p.add_argument("--max-n", type=int)
    p.add_argument("--min-d", type=int)
    p.add_argument("--max-d", type=int, default=80)
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--dps", type=int, default=200)
    p.add_argument("--max-gamma-index", type=int)
    p.add_argument("--tol", type=float, default=1e-8)
    p.add_argument("--maxsteps", type=int, default=1000)
    p.add_argument("--extraprec", type=int, default=150)
    p.add_argument("--solver", choices=["scaled", "raw", "auto"], default="scaled")
    p.add_argument("--append", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()

    rows_path = Path(args.rows)
    rows = load_csv(rows_path)
    if not rows:
        raise SystemExit(f"No rows found in {rows_path}")

    out_path = Path(args.out)
    existing = load_csv(out_path) if args.append else []
    skip_keys = {row_key(r) for r in existing}

    selected = select_rows(
        rows,
        status=args.status,
        c_values=parse_c_list(args.c_values),
        min_n=args.min_n,
        max_n=args.max_n,
        min_d=args.min_d,
        max_d=args.max_d,
        limit=args.limit,
        skip_keys=skip_keys,
    )

    if not selected:
        print("No rows selected.")
        return

    max_gamma_index = args.max_gamma_index
    if max_gamma_index is None:
        max_gamma_index = max(int(float(r["n"])) + int(float(r["d"])) for r in selected) + 4

    print(f"Rows loaded: {len(rows)}")
    print(f"Rows selected: {len(selected)}")
    print(f"Existing skipped: {len(skip_keys)}")
    print(f"dps: {args.dps}")
    print(f"max_gamma_index: {max_gamma_index}")
    print(f"solver: {args.solver}")
    print(f"out: {out_path}")

    mp.mp.dps = args.dps
    gammas = F.xi_gammas_cached(max_gamma_index, dps=args.dps, cache_dir=".gamma_cache", verbose=True)

    results = []
    t0 = time.perf_counter()

    for i, row in enumerate(selected, start=1):
        target = to_deepcheck_target(row)
        print(
            f"[{i}/{len(selected)}] deepchecking c={target['c']} n={target['n']} d={target['d']} "
            f"status={row.get('certified_status', '')} ...",
            flush=True,
        )
        rt0 = time.perf_counter()
        try:
            result = D.deepcheck_one(
                target,
                gammas,
                tol=args.tol,
                maxsteps=args.maxsteps,
                extraprec=args.extraprec,
                solver=args.solver,
            )
            result["seconds"] = time.perf_counter() - rt0
        except Exception as e:
            result = failed_result(target, e, time.perf_counter() - rt0)
        results.append(result)

    elapsed = time.perf_counter() - t0

    if args.append:
        append_csv(results, out_path)
        all_results = existing + results
    else:
        write_csv(results, out_path)
        all_results = results

    ok = [r for r in results if r.get("status") == "ok"]
    failed = [r for r in results if r.get("status") == "failed"]
    match_current_cert = [r for r in ok if r.get("match_lo") is True]
    changed_current_cert = [r for r in ok if r.get("match_lo") is False]

    summary = {
        "input_rows": str(rows_path),
        "out": str(out_path),
        "rows_loaded": len(rows),
        "rows_selected_this_batch": len(selected),
        "existing_skipped": len(skip_keys),
        "ok_this_batch": len(ok),
        "failed_this_batch": len(failed),
        "match_current_cert_this_batch": len(match_current_cert),
        "changed_current_cert_this_batch": len(changed_current_cert),
        "total_output_rows": len(all_results),
        "elapsed_seconds": elapsed,
        "config": {
            "status": args.status,
            "c_values": args.c_values,
            "min_n": args.min_n,
            "max_n": args.max_n,
            "min_d": args.min_d,
            "max_d": args.max_d,
            "limit": args.limit,
            "dps": args.dps,
            "max_gamma_index": max_gamma_index,
            "tol": args.tol,
            "maxsteps": args.maxsteps,
            "extraprec": args.extraprec,
            "solver": args.solver,
            "append": args.append,
        },
    }

    Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nDone.")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_path}")
    print(f"Wrote {args.summary_json}")


if __name__ == "__main__":
    main()
