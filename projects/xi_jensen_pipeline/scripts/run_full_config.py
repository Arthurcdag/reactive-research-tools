"""
Run the client's exact config through the fast pipeline, time it end-to-end,
and produce xi_jensen_scan_fast.csv.

We also time xi_gammas at an intermediate max_index so we can extrapolate
what the baseline would have taken.
"""
from __future__ import annotations

import time
from pathlib import Path

import mpmath as mp

import xi_jensen_fast as F


def main():
    dps = 100
    max_gamma_index = 24
    c_values = [0.50, 0.54, 0.56, 0.57, 0.60, 0.70]
    n_values = range(3, 15)

    print(f"Config: dps={dps}, max_gamma_index={max_gamma_index}, "
          f"c_values={c_values}, n_values={list(n_values)}")
    print("Backend:", mp.libmp.BACKEND)

    # Cold run
    (Path(".gamma_cache") / "." ).parent.mkdir(exist_ok=True)
    for f in Path(".gamma_cache").glob("*"):
        f.unlink()
    t0 = time.perf_counter()
    gammas, rows = F.run(
        dps=dps,
        max_gamma_index=max_gamma_index,
        c_values=c_values,
        n_values=n_values,
        out_csv=Path("xi_jensen_scan_fast.csv"),
        root_method="numpy",
        use_cache=True,
        use_parallel=False,
        verbose=False,
    )
    t_cold = time.perf_counter() - t0
    print(f"cold run (compute + cache + scan): {t_cold:.2f} s   rows={len(rows)}")

    # Warm run (cache hit)
    t0 = time.perf_counter()
    F.run(
        dps=dps,
        max_gamma_index=max_gamma_index,
        c_values=c_values,
        n_values=n_values,
        out_csv=Path("xi_jensen_scan_fast.csv"),
        root_method="numpy",
        use_cache=True,
        use_parallel=False,
    )
    t_warm = time.perf_counter() - t0
    print(f"warm run (cache hit): {t_warm:.3f} s")


if __name__ == "__main__":
    main()
