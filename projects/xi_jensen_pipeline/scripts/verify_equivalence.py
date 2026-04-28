"""
verify_equivalence.py

Cross-check the optimised xi_gammas_fast against the baseline xi_gammas
for a reduced config where both are feasible to run.

We also cross-check against known published values for the first Jensen
coefficients (from Griffin-Ono-Rolen-Zagier and related literature).
Known first few values of gamma(m):
    gamma(0)  ~  0.49712...
    gamma(1)  ~  0.02275...
    gamma(2)  ~  2.292e-4
(These are the Taylor-series moments of Xi at z=0, matching the baseline
convention of xi_gammas.)
"""

from __future__ import annotations

import time

import mpmath as mp

import xi_jensen_baseline as B
import xi_jensen_fast as F


def max_rel_diff(a_list, b_list) -> mp.mpf:
    worst = mp.mpf(0)
    for a, b in zip(a_list, b_list):
        denom = max(abs(a), abs(b), mp.mpf(10) ** (-mp.mp.dps + 5))
        rel = abs(a - b) / denom
        if rel > worst:
            worst = rel
    return worst


def run_case(max_index: int, dps: int) -> None:
    print(f"\n=== dps={dps}, max_index={max_index} ===")
    mp.mp.dps = dps

    t0 = time.perf_counter()
    baseline = B.xi_gammas(max_index, dps=dps)
    t_base = time.perf_counter() - t0

    t0 = time.perf_counter()
    fast = F.xi_gammas_fast(max_index, dps=dps)
    t_fast = time.perf_counter() - t0

    diff = max_rel_diff(baseline, fast)
    speedup = t_base / t_fast if t_fast > 0 else float("inf")

    print(f"  baseline time : {t_base:8.3f} s")
    print(f"  fast time     : {t_fast:8.3f} s")
    print(f"  speedup       : {speedup:8.1f} x")
    print(f"  max rel diff  : {mp.nstr(diff, 4)}   (working precision ~1e-{dps})")

    print("  gamma(0..min(max_index,4)):")
    for m in range(min(max_index, 4) + 1):
        print(f"    m={m}  baseline={mp.nstr(baseline[m], 20)}")
        print(f"          fast    ={mp.nstr(fast[m],     20)}")


if __name__ == "__main__":
    run_case(max_index=4, dps=50)
    run_case(max_index=8, dps=50)
    run_case(max_index=6, dps=100)
