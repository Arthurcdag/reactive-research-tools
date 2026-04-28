"""
High-precision sensitivity check.

For each row in the default config, re-run with dps=150 AND mp.polyroots,
then compare endpoint_state / defect_location labels against the numpy-float64
result. Rows whose classification depends on a near-tie root (small |Im|
close to the tolerance) would flip; any flips are flagged.

This directly supports the client's requirement:
    "Verify sensitive cases with higher precision."
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import mpmath as mp

import xi_jensen_fast as F


def rows_dict(path: str | Path):
    with Path(path).open() as f:
        return {(r["c"], r["n"]): r for r in csv.DictReader(f)}


def main() -> None:
    dps_lo = 100
    dps_hi = 150
    max_gamma_index = 24
    c_values = [0.50, 0.54, 0.56, 0.57, 0.60, 0.70]
    n_values = list(range(3, 15))

    t0 = time.perf_counter()
    mp.mp.dps = dps_lo
    gammas_lo = F.xi_gammas_cached(max_gamma_index, dps=dps_lo)
    rows_lo = []
    for c in c_values:
        rows_lo.extend(F.scan_ray(gammas_lo, c, n_values, root_method="numpy"))
    t_lo = time.perf_counter() - t0
    print(f"lo (dps={dps_lo}, numpy roots): {len(rows_lo)} rows in {t_lo:.2f} s")

    t0 = time.perf_counter()
    mp.mp.dps = dps_hi
    gammas_hi = F.xi_gammas_cached(max_gamma_index, dps=dps_hi)
    rows_hi = []
    for c in c_values:
        rows_hi.extend(F.scan_ray(gammas_hi, c, n_values, root_method="mpmath"))
    t_hi = time.perf_counter() - t0
    print(f"hi (dps={dps_hi}, mp.polyroots): {len(rows_hi)} rows in {t_hi:.2f} s")

    assert len(rows_lo) == len(rows_hi)
    mismatches = 0
    for a, b in zip(rows_lo, rows_hi):
        if (a.c, a.n, a.d) != (b.c, b.n, b.d):
            print(f"row-key mismatch: {a} vs {b}")
            mismatches += 1
            continue
        same_state = a.endpoint_state == b.endpoint_state
        same_defect = a.defect_location == b.defect_location
        same_deficit = a.real_root_deficit == b.real_root_deficit
        if not (same_state and same_defect and same_deficit):
            mismatches += 1
            print(
                f"flip at c={a.c} n={a.n} d={a.d}: "
                f"state {a.endpoint_state}->{b.endpoint_state}, "
                f"defect {a.defect_location}->{b.defect_location}, "
                f"deficit {a.real_root_deficit}->{b.real_root_deficit}"
            )

    print(f"\nlabel mismatches (lo vs hi): {mismatches} / {len(rows_lo)}")
    if mismatches == 0:
        print("All classifications stable under higher precision + mp.polyroots. PASS.")


if __name__ == "__main__":
    main()
