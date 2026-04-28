#!/usr/bin/env python3
"""
xi_jensen_fast_experiments.py

Experiment runner built on top of xi_jensen_fast.

Design goals
------------
- Keep the optimized moment-integral + cache engine.
- Keep numpy roots as the default main scan path.
- Add larger-n presets for actual threshold experiments.
- Auto-size max_gamma_index from (c_values, n_values) when desired.
- Optionally verify only *sensitive* rows with mp.polyroots.

This evolves the fast branch rather than switching the whole scan to polyroots.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import mpmath as mp
import numpy as np

import xi_jensen_fast as F


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def auto_max_gamma_index(c_values: Iterable[float], n_values: Iterable[int], safety: int = 4) -> int:
    n_values = list(n_values)
    max_need = 0
    for c in c_values:
        for n in n_values:
            d = F.threshold_degree(n, c)
            max_need = max(max_need, n + d)
    return max_need + safety


def rows_from_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def md5_normalized_csv(path: Path) -> str:
    import hashlib
    data = path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    return hashlib.md5(data).hexdigest()


# ---------------------------------------------------------------------------
# Detailed scan with optional sensitive verification
# ---------------------------------------------------------------------------

@dataclass
class DetailedRow:
    c: float
    n: int
    d: int
    c_nd: float
    real_root_deficit: int
    endpoint_state: str
    defect_location: str
    min_nonreal_abs_imag: float
    sensitive: bool
    verified: bool
    verified_match: bool | None
    hi_real_root_deficit: int | None
    hi_endpoint_state: str | None
    hi_defect_location: str | None


def roots_numpy(coeffs_ascending) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def min_nonreal_abs_imag(roots, tol: float = 1e-8) -> float:
    vals = [abs(complex(z).imag) for z in roots if abs(complex(z).imag) > tol]
    return min(vals) if vals else 0.0


def classify_row_from_roots(c: float, n: int, d: int, roots, tol: float = 1e-8):
    real_count = F.count_real_roots(roots, tol=tol)
    return {
        "c": c,
        "n": n,
        "d": d,
        "c_nd": F.c_nd(n, d),
        "real_root_deficit": int(d - real_count),
        "endpoint_state": F.endpoint_state_proxy(roots, tol=tol),
        "defect_location": F.defect_location_proxy(roots, tol=tol),
    }


def scan_ray_detailed(
    gammas,
    c: float,
    n_values: Iterable[int],
    *,
    real_tol: float = 1e-8,
    verify_sensitive: bool = False,
    verify_factor: float = 50.0,
    hi_dps: int = 150,
):
    rows: list[DetailedRow] = []

    # High-precision gamma table loaded lazily only if needed.
    hi_gammas = None

    for n in n_values:
        d = F.threshold_degree(n, c)
        if d <= 0 or n + d >= len(gammas):
            continue

        coeffs = F.jensen_coeffs(gammas, n, d)
        roots_lo = roots_numpy(coeffs)
        base = classify_row_from_roots(c, n, d, roots_lo, tol=real_tol)

        min_im = min_nonreal_abs_imag(roots_lo, tol=real_tol)
        sensitive = (min_im != 0.0 and min_im <= verify_factor * real_tol)

        verified = False
        verified_match = None
        hi_deficit = None
        hi_state = None
        hi_loc = None

        if verify_sensitive and sensitive:
            if hi_gammas is None:
                hi_gammas = F.xi_gammas_cached(
                    max_index=len(gammas) - 1,
                    dps=hi_dps,
                    cache_dir=".gamma_cache",
                    verbose=False,
                )

            coeffs_hi = F.jensen_coeffs(hi_gammas, n, d)
            roots_hi = F.roots_mpmath(coeffs_hi, maxsteps=200, cleanup=True, extraprec=50)
            hi = classify_row_from_roots(c, n, d, roots_hi, tol=real_tol)

            verified = True
            hi_deficit = hi["real_root_deficit"]
            hi_state = hi["endpoint_state"]
            hi_loc = hi["defect_location"]
            verified_match = (
                base["real_root_deficit"] == hi_deficit
                and base["endpoint_state"] == hi_state
                and base["defect_location"] == hi_loc
            )

        rows.append(
            DetailedRow(
                c=c,
                n=n,
                d=d,
                c_nd=base["c_nd"],
                real_root_deficit=base["real_root_deficit"],
                endpoint_state=base["endpoint_state"],
                defect_location=base["defect_location"],
                min_nonreal_abs_imag=float(min_im),
                sensitive=bool(sensitive),
                verified=verified,
                verified_match=verified_match,
                hi_real_root_deficit=hi_deficit,
                hi_endpoint_state=hi_state,
                hi_defect_location=hi_loc,
            )
        )

    return rows


def write_detailed_csv(rows: list[DetailedRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize_detailed_rows(rows: list[DetailedRow]) -> dict:
    if not rows:
        return {
            "row_count": 0,
            "first_defect": None,
            "defect_rows": 0,
            "endpoint_state_counts": {},
            "defect_location_counts": {},
            "sensitive_rows": 0,
            "verified_rows": 0,
            "verification_mismatches": 0,
        }

    defects = [r for r in rows if r.real_root_deficit > 0]
    by_c: dict[str, dict] = {}

    grouped: dict[float, list[DetailedRow]] = defaultdict(list)
    for r in rows:
        grouped[r.c].append(r)

    for c, grp in sorted(grouped.items()):
        gdef = [r for r in grp if r.real_root_deficit > 0]
        state_counts = Counter(r.endpoint_state for r in grp)
        loc_counts = Counter(r.defect_location for r in gdef)
        sens = [r for r in grp if r.sensitive]
        ver = [r for r in grp if r.verified]
        mism = [r for r in grp if r.verified and r.verified_match is False]

        by_c[str(c)] = {
            "row_count": len(grp),
            "first_defect": asdict(gdef[0]) if gdef else None,
            "defect_rows": len(gdef),
            "endpoint_state_counts": dict(state_counts),
            "defect_location_counts": dict(loc_counts),
            "sensitive_rows": len(sens),
            "verified_rows": len(ver),
            "verification_mismatches": len(mism),
            "n_range": [min(r.n for r in grp), max(r.n for r in grp)],
            "d_range": [min(r.d for r in grp), max(r.d for r in grp)],
        }

    sens_all = [r for r in rows if r.sensitive]
    ver_all = [r for r in rows if r.verified]
    mism_all = [r for r in rows if r.verified and r.verified_match is False]

    return {
        "row_count": len(rows),
        "first_defect": asdict(defects[0]) if defects else None,
        "defect_rows": len(defects),
        "endpoint_state_counts": dict(Counter(r.endpoint_state for r in rows)),
        "defect_location_counts": dict(Counter(r.defect_location for r in defects)),
        "sensitive_rows": len(sens_all),
        "verified_rows": len(ver_all),
        "verification_mismatches": len(mism_all),
        "by_c": by_c,
    }


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict] = {
    "client_full": {
        "dps": 100,
        "c_values": [0.50, 0.54, 0.56, 0.57, 0.60, 0.70],
        "n_values": list(range(3, 15)),
        "max_gamma_index": 24,
        "out_csv": "xi_jensen_fast_exp_client_full.csv",
        "verify_sensitive": False,
    },
    "c070_extended": {
        "dps": 100,
        "c_values": [0.70],
        "n_values": list(range(3, 61)),
        "max_gamma_index": None,
        "out_csv": "xi_jensen_fast_exp_c070_extended.csv",
        "verify_sensitive": True,
    },
    "c060_extended": {
        "dps": 110,
        "c_values": [0.60],
        "n_values": list(range(3, 181)),
        "max_gamma_index": None,
        "out_csv": "xi_jensen_fast_exp_c060_extended.csv",
        "verify_sensitive": True,
    },
    "threshold_band_extended": {
        "dps": 120,
        "c_values": [0.56, 0.57, 0.58],
        "n_values": list(range(3, 81)),
        "max_gamma_index": None,
        "out_csv": "xi_jensen_fast_exp_threshold_band_extended.csv",
        "verify_sensitive": True,
    },
    "fixed_small_validation": {
        "dps": 80,
        "c_values": [0.70],
        "n_values": list(range(3, 21)),
        "max_gamma_index": 40,
        "out_csv": "xi_jensen_fast_exp_fixed_small_validation.csv",
        "verify_sensitive": True,
    },
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Extended experiment runner for xi_jensen_fast")
    p.add_argument("--preset", choices=sorted(PRESETS.keys()), default="client_full")
    p.add_argument("--summary-json", type=str, help="Optional JSON summary path")
    p.add_argument("--out-csv", type=str, help="Override CSV output path")
    p.add_argument("--verify-sensitive", action="store_true", help="Verify only sensitive rows with mp.polyroots")
    p.add_argument("--no-verify-sensitive", action="store_true", help="Force verification off")
    p.add_argument("--verify-factor", type=float, default=50.0, help="Sensitive iff min_nonreal_abs_imag <= factor * tol")
    p.add_argument("--hi-dps", type=int, default=150)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = PRESETS[args.preset].copy()

    if cfg["max_gamma_index"] is None:
        cfg["max_gamma_index"] = auto_max_gamma_index(cfg["c_values"], cfg["n_values"])

    if args.out_csv:
        cfg["out_csv"] = args.out_csv
    if args.verify_sensitive:
        cfg["verify_sensitive"] = True
    if args.no_verify_sensitive:
        cfg["verify_sensitive"] = False

    out_csv = Path(cfg["out_csv"])

    print("Running preset:", args.preset)
    print("Config:", cfg)

    gammas = F.xi_gammas_cached(
        max_index=cfg["max_gamma_index"],
        dps=cfg["dps"],
        cache_dir=".gamma_cache",
        verbose=args.verbose,
    )

    rows: list[DetailedRow] = []
    for c in cfg["c_values"]:
        rows.extend(
            scan_ray_detailed(
                gammas,
                c,
                cfg["n_values"],
                verify_sensitive=cfg["verify_sensitive"],
                verify_factor=args.verify_factor,
                hi_dps=args.hi_dps,
            )
        )

    if rows:
        write_detailed_csv(rows, out_csv)

    summary = {
        "preset": args.preset,
        "config": cfg,
        "summary": summarize_detailed_rows(rows),
        "out_csv": str(out_csv),
        "out_csv_md5_normalized": md5_normalized_csv(out_csv) if rows else None,
    }

    print("\nSummary:")
    print(json.dumps(summary["summary"], indent=2))

    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nWrote summary JSON to {args.summary_json}")


if __name__ == "__main__":
    main()
