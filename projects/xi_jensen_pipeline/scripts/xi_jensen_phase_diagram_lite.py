#!/usr/bin/env python3
"""
xi_jensen_phase_diagram_lite.py

A lighter, faster emulation version of the Xi–Jensen application script.
It is meant to validate the computational pipeline in-session, not to test
the full asymptotic threshold theory.

This version:
- uses smaller max_gamma_index
- uses lower precision
- scans a tiny n-range
- uses numpy roots for speed
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import mpmath as mp
import numpy as np


def Xi(z: mp.mpf | mp.mpc) -> mp.mpc:
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def xi_gammas(max_index: int, dps: int = 30) -> list[mp.mpf]:
    mp.mp.dps = dps
    taylor = mp.taylor(Xi, 0, 2 * max_index)
    gammas: list[mp.mpf] = []
    for m in range(max_index + 1):
        a_2m = mp.mpf(taylor[2 * m])
        gamma_m = ((-1) ** m) * a_2m * mp.factorial(2 * m)
        gammas.append(mp.re(gamma_m))
    return gammas


def threshold_degree(n: int, c: float) -> int:
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def c_nd(n: int, d: int) -> float:
    return d * math.sqrt(math.log(n)) / (n ** 1.5)


def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending: list[mp.mpf]) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def count_real_roots(roots, tol: float = 1e-8) -> int:
    return sum(abs(z.imag) <= tol for z in roots)


def endpoint_state_proxy(roots, tol: float = 1e-8) -> str:
    return "2" if count_real_roots(roots, tol) == len(roots) else "0"


def defect_location_proxy(roots, tol: float = 1e-8) -> str:
    roots = np.array(list(roots), dtype=np.complex128)
    nonreal = roots[np.abs(roots.imag) > tol]
    if len(nonreal) == 0:
        return "none"
    candidate = nonreal[np.argmin(np.abs(nonreal.imag))]
    if np.isclose(candidate.real, np.min(roots.real), atol=1e-8):
        return "endpoint_like"
    return "bulk_like"


def main() -> None:
    dps = 30
    max_gamma_index = 10
    c_values = [0.50, 0.57, 0.70]
    n_values = range(3, 9)
    out_csv = Path("xi_jensen_lite_scan.csv")

    gammas = xi_gammas(max_index=max_gamma_index, dps=dps)

    rows = []
    for c in c_values:
        for n in n_values:
            d = threshold_degree(n, c)
            if d <= 0 or n + d >= len(gammas):
                continue
            coeffs = jensen_coeffs(gammas, n, d)
            roots = roots_numpy(coeffs)
            real_count = count_real_roots(roots)
            rows.append({
                "c": c,
                "n": n,
                "d": d,
                "c_nd": c_nd(n, d),
                "real_root_deficit": d - real_count,
                "endpoint_state": endpoint_state_proxy(roots),
                "defect_location": defect_location_proxy(roots),
            })

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {out_csv.resolve()}")
    for row in rows[:10]:
        print(row)


if __name__ == "__main__":
    main()
