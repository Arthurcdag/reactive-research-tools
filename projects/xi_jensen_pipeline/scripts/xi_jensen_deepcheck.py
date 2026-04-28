#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import mpmath as mp
import numpy as np

import xi_jensen_fast as F


def load_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def row_key(r: dict) -> tuple[str, str, str]:
    return (str(r["c"]), str(r["n"]), str(r["d"]))


def merge_inputs(mismatches: list[dict], failures: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for tag, rows in [("mismatch", mismatches), ("failure", failures)]:
        for r in rows:
            key = row_key(r)
            if key in seen:
                continue
            seen.add(key)
            rr = dict(r)
            rr["deepcheck_source"] = tag
            out.append(rr)
    return out


def poly_eval_ascending(coeffs, z):
    total = mp.mpc("0")
    for c in reversed(coeffs):
        total = total * z + c
    return total


def relative_residual(coeffs, z):
    num = abs(poly_eval_ascending(coeffs, z))
    denom = mp.mpf("0")
    az = abs(z)
    p = mp.mpf("1")
    for c in coeffs:
        denom += abs(c) * p
        p *= az
    if denom == 0:
        return float(num)
    return float(num / denom)


def residual_stats(coeffs, roots):
    if not roots:
        return {
            "max_rel_residual": "",
            "median_rel_residual": "",
        }
    vals = sorted(relative_residual(coeffs, z) for z in roots)
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else 0.5 * (vals[mid - 1] + vals[mid])
    return {
        "max_rel_residual": max(vals),
        "median_rel_residual": median,
    }


def roots_polyroots_scaled(coeffs_ascending, *, maxsteps: int, extraprec: int):
    """
    Scale polynomial before mp.polyroots.

    We solve p(x)=0 by x = s*y. The scale s is chosen from a Cauchy-style
    root bound. Several candidate scales are tried.
    """
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    while len(desc) > 1 and abs(desc[0]) == 0:
        desc = desc[1:]

    lead = desc[0]
    monic = [z / lead for z in desc]
    deg = len(monic) - 1
    if deg <= 0:
        return []

    B = 1 + max(abs(z) for z in monic[1:])
    scales = [
        mp.sqrt(B),
        mp.nthroot(B, 3),
        B,
        mp.mpf("1"),
        mp.mpf("0.5") * mp.sqrt(B),
        mp.mpf("2") * mp.sqrt(B),
    ]

    attempts = [
        {"maxsteps": maxsteps, "cleanup": False, "extraprec": extraprec},
        {"maxsteps": maxsteps * 2, "cleanup": False, "extraprec": extraprec + 50},
        {"maxsteps": maxsteps * 4, "cleanup": False, "extraprec": extraprec + 100},
    ]

    last_err = None
    for s in scales:
        scaled = [monic[k] * (s ** (deg - k)) for k in range(deg + 1)]
        scaled = [z / scaled[0] for z in scaled]
        for opts in attempts:
            try:
                roots_y = mp.polyroots(scaled, **opts)
                return [s * r for r in roots_y], f"scaled:s={mp.nstr(s, 8)},opts={opts}"
            except Exception as e:
                last_err = e

    raise last_err


def roots_polyroots_raw(coeffs_ascending, *, maxsteps: int, extraprec: int):
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    roots = mp.polyroots(desc, maxsteps=maxsteps, cleanup=False, extraprec=extraprec)
    return roots, "raw"


def classify_roots(roots, d: int, tol: float):
    real_count = F.count_real_roots(roots, tol=tol)
    return {
        "deep_real_root_deficit": int(d - real_count),
        "deep_endpoint_state": F.endpoint_state_proxy(roots, tol=tol),
        "deep_defect_location": F.defect_location_proxy(roots, tol=tol),
    }


def safe_get(r, key, default=""):
    return r.get(key, default)


def deepcheck_one(row: dict, gammas, *, tol: float, maxsteps: int, extraprec: int, solver: str):
    c = float(row["c"])
    n = int(row["n"])
    d = int(row["d"])
    coeffs = F.jensen_coeffs(gammas, n, d)

    if solver == "raw":
        roots, method = roots_polyroots_raw(coeffs, maxsteps=maxsteps, extraprec=extraprec)
    elif solver == "scaled":
        roots, method = roots_polyroots_scaled(coeffs, maxsteps=maxsteps, extraprec=extraprec)
    else:
        try:
            roots, method = roots_polyroots_scaled(coeffs, maxsteps=maxsteps, extraprec=extraprec)
        except Exception:
            roots, method = roots_polyroots_raw(coeffs, maxsteps=maxsteps * 2, extraprec=extraprec + 100)

    cls = classify_roots(roots, d=d, tol=tol)
    res = residual_stats(coeffs, roots)

    lo_deficit = safe_get(row, "lo_real_root_deficit", safe_get(row, "real_root_deficit", ""))
    lo_state = safe_get(row, "lo_endpoint_state", safe_get(row, "endpoint_state", ""))
    lo_loc = safe_get(row, "lo_defect_location", safe_get(row, "defect_location", ""))

    old_hi_deficit = safe_get(row, "hi_real_root_deficit", "")
    old_hi_state = safe_get(row, "hi_endpoint_state", "")
    old_hi_loc = safe_get(row, "hi_defect_location", "")

    match_lo = (
        str(lo_deficit) == str(cls["deep_real_root_deficit"])
        and str(lo_state) == str(cls["deep_endpoint_state"])
        and str(lo_loc) == str(cls["deep_defect_location"])
    )

    match_old_hi = ""
    if old_hi_deficit != "":
        match_old_hi = (
            str(old_hi_deficit) == str(cls["deep_real_root_deficit"])
            and str(old_hi_state) == str(cls["deep_endpoint_state"])
            and str(old_hi_loc) == str(cls["deep_defect_location"])
        )

    return {
        "source": row.get("deepcheck_source", ""),
        "c": c,
        "n": n,
        "d": d,
        "lo_real_root_deficit": lo_deficit,
        "lo_endpoint_state": lo_state,
        "lo_defect_location": lo_loc,
        "old_hi_real_root_deficit": old_hi_deficit,
        "old_hi_endpoint_state": old_hi_state,
        "old_hi_defect_location": old_hi_loc,
        **cls,
        "match_lo": match_lo,
        "match_old_hi": match_old_hi,
        "method": method,
        **res,
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


def write_markdown(summary: dict, rows: list[dict], path: Path) -> None:
    lines = []
    lines.append("# Xi-Jensen deepcheck report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for k, v in summary.items():
        if k != "config":
            lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for k, v in summary["config"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Rows")
    lines.append("")
    for r in rows:
        lines.append(
            f"- {r.get('source')} c={r.get('c')} n={r.get('n')} d={r.get('d')}: "
            f"lo=({r.get('lo_real_root_deficit')},{r.get('lo_defect_location')}), "
            f"old_hi=({r.get('old_hi_real_root_deficit')},{r.get('old_hi_defect_location')}), "
            f"deep=({r.get('deep_real_root_deficit')},{r.get('deep_defect_location')}), "
            f"match_lo={r.get('match_lo')}, match_old_hi={r.get('match_old_hi')}, "
            f"resid_max={r.get('max_rel_residual')}, status={r.get('status')}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    p = argparse.ArgumentParser(description="Deepcheck Xi-Jensen mismatch/failure rows with scaled high-precision polyroots")
    p.add_argument("--mismatches", default="xi_jensen_verify_triage_mismatches.csv")
    p.add_argument("--failures", default="xi_jensen_verify_triage_failures.csv")
    p.add_argument("--out", default="xi_jensen_deepcheck_results.csv")
    p.add_argument("--summary-json", default="xi_jensen_deepcheck_summary.json")
    p.add_argument("--report-md", default="xi_jensen_deepcheck_report.md")
    p.add_argument("--dps", type=int, default=200)
    p.add_argument("--max-gamma-index", type=int, default=None)
    p.add_argument("--tol", type=float, default=1e-8)
    p.add_argument("--maxsteps", type=int, default=1000)
    p.add_argument("--extraprec", type=int, default=150)
    p.add_argument("--solver", choices=["scaled", "raw", "auto"], default="scaled")
    p.add_argument("--limit", type=int)
    p.add_argument("--include-failures", action="store_true", help="Also deepcheck failure rows")
    return p.parse_args()


def main():
    args = parse_args()

    mismatches = load_csv(Path(args.mismatches))
    failures = load_csv(Path(args.failures)) if args.include_failures else []
    targets = merge_inputs(mismatches, failures)
    if args.limit is not None:
        targets = targets[:args.limit]

    if not targets:
        print("No rows to deepcheck.")
        return

    max_gamma_index = args.max_gamma_index
    if max_gamma_index is None:
        max_gamma_index = max(int(r["n"]) + int(r["d"]) for r in targets) + 4

    print(f"Deepcheck rows: {len(targets)}")
    print(f"dps: {args.dps}")
    print(f"max_gamma_index: {max_gamma_index}")
    print(f"solver: {args.solver}")

    mp.mp.dps = args.dps
    gammas = F.xi_gammas_cached(max_gamma_index, dps=args.dps, cache_dir=".gamma_cache", verbose=True)

    results = []
    t0 = time.perf_counter()
    for i, row in enumerate(targets, start=1):
        print(f"[{i}/{len(targets)}] c={row['c']} n={row['n']} d={row['d']} source={row.get('deepcheck_source','')} ...", flush=True)
        rt0 = time.perf_counter()
        try:
            result = deepcheck_one(
                row,
                gammas,
                tol=args.tol,
                maxsteps=args.maxsteps,
                extraprec=args.extraprec,
                solver=args.solver,
            )
        except Exception as e:
            result = {
                "source": row.get("deepcheck_source", ""),
                "c": float(row["c"]),
                "n": int(row["n"]),
                "d": int(row["d"]),
                "lo_real_root_deficit": safe_get(row, "lo_real_root_deficit", safe_get(row, "real_root_deficit", "")),
                "lo_endpoint_state": safe_get(row, "lo_endpoint_state", safe_get(row, "endpoint_state", "")),
                "lo_defect_location": safe_get(row, "lo_defect_location", safe_get(row, "defect_location", "")),
                "old_hi_real_root_deficit": safe_get(row, "hi_real_root_deficit", ""),
                "old_hi_endpoint_state": safe_get(row, "hi_endpoint_state", ""),
                "old_hi_defect_location": safe_get(row, "hi_defect_location", ""),
                "deep_real_root_deficit": "",
                "deep_endpoint_state": "",
                "deep_defect_location": "",
                "match_lo": "",
                "match_old_hi": "",
                "method": "",
                "max_rel_residual": "",
                "median_rel_residual": "",
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            }
        result["seconds"] = time.perf_counter() - rt0
        results.append(result)

    elapsed = time.perf_counter() - t0

    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] == "failed"]
    match_lo = [r for r in ok if r["match_lo"] is True]
    match_old_hi = [r for r in ok if r["match_old_hi"] is True]

    summary = {
        "targets": len(targets),
        "ok": len(ok),
        "failed": len(failed),
        "match_lo": len(match_lo),
        "match_old_hi": len(match_old_hi),
        "elapsed_seconds": elapsed,
        "config": {
            "mismatches": args.mismatches,
            "failures": args.failures,
            "include_failures": args.include_failures,
            "dps": args.dps,
            "max_gamma_index": max_gamma_index,
            "tol": args.tol,
            "maxsteps": args.maxsteps,
            "extraprec": args.extraprec,
            "solver": args.solver,
            "limit": args.limit,
        },
    }

    write_csv(results, Path(args.out))
    Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(summary, results, Path(args.report_md))

    print("\nDone.")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.out}")
    print(f"Wrote {args.summary_json}")
    print(f"Wrote {args.report_md}")


if __name__ == "__main__":
    main()
