"""
Profile the baseline to pinpoint the bottleneck.

We run a reduced config and break xi_gammas timing apart from scan timing.
"""
from __future__ import annotations

import cProfile
import pstats
import time
from io import StringIO
from pathlib import Path

import mpmath as mp

import xi_jensen_baseline as B


def time_it(label, fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    dt = time.perf_counter() - t0
    print(f"[time] {label}: {dt:.3f} s")
    return out, dt


def main():
    # Small config to get something that finishes quickly but still exercises
    # the same code paths (Xi Taylor, polynomial root-finding).
    dps = 50
    max_gamma_index = 8
    c_values = [0.5, 0.6, 0.7]
    n_values = range(3, 10)

    print(f"Profiling baseline at dps={dps}, max_gamma_index={max_gamma_index}")
    mp.mp.dps = dps

    gammas, t_gammas = time_it("xi_gammas", B.xi_gammas, max_gamma_index, dps=dps)

    def do_scans():
        out = []
        for c in c_values:
            out.extend(B.scan_ray(gammas, c, n_values, root_method="numpy"))
        return out

    _, t_scan = time_it("scan (all c-rays)", do_scans)

    print(f"[ratio] xi_gammas / total = {t_gammas / (t_gammas + t_scan):.1%}")

    # cProfile, to confirm which mpmath calls dominate inside xi_gammas.
    prof = cProfile.Profile()
    prof.enable()
    B.xi_gammas(max_gamma_index, dps=dps)
    prof.disable()

    s = StringIO()
    pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(15)
    print("\nTop cumulative time inside xi_gammas:")
    print(s.getvalue())


if __name__ == "__main__":
    main()
