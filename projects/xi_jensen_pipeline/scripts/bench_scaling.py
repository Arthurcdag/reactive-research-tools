"""
Measure how each method scales in max_gamma_index (at fixed dps) and in dps
(at fixed max_gamma_index). The baseline is expected to blow up; the fast
method should grow linearly.
"""
from __future__ import annotations

import time

import mpmath as mp

import xi_jensen_baseline as B
import xi_jensen_fast as F


def bench(label, fn, *a, **kw):
    t0 = time.perf_counter()
    fn(*a, **kw)
    return time.perf_counter() - t0


def scaling_in_max_index(dps: int, idx_list) -> None:
    print(f"\n--- scaling in max_gamma_index at dps={dps} ---")
    print(f"{'max_idx':>8} {'baseline(s)':>14} {'fast(s)':>10} {'speedup':>10}")
    for mi in idx_list:
        t_b = bench("base", B.xi_gammas, mi, dps=dps)
        t_f = bench("fast", F.xi_gammas_fast, mi, dps=dps)
        print(f"{mi:>8} {t_b:>14.3f} {t_f:>10.3f} {t_b/t_f:>10.1f}x")


def scaling_in_dps(max_index: int, dps_list) -> None:
    print(f"\n--- scaling in dps at max_gamma_index={max_index} ---")
    print(f"{'dps':>5} {'baseline(s)':>14} {'fast(s)':>10} {'speedup':>10}")
    for d in dps_list:
        t_b = bench("base", B.xi_gammas, max_index, dps=d)
        t_f = bench("fast", F.xi_gammas_fast, max_index, dps=d)
        print(f"{d:>5} {t_b:>14.3f} {t_f:>10.3f} {t_b/t_f:>10.1f}x")


if __name__ == "__main__":
    scaling_in_max_index(dps=50, idx_list=[4, 8, 12, 16])
    scaling_in_dps(max_index=6, dps_list=[30, 50, 75, 100])
