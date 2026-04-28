#!/usr/bin/env python3
"""
xi_jensen_phase_diagram.py

Research application scaffold for the threshold-scale Jensen polynomial theory.

Main tasks
----------
1. Compute Taylor coefficients of Xi(z) = xi(1/2 + i z) around z = 0.
2. Convert them into Jensen coefficients gamma(n) from
       Xi(z) = sum_{m>=0} (-1)^m gamma(m) z^(2m)/(2m)!.
3. Build Jensen polynomials
       J_{d,n}(X) = sum_{j=0}^d binom(d,j) gamma(n+j) X^j.
4. Compute roots and record:
       - real-root deficit
       - endpoint-state proxy
       - defect localization proxy
       - cumulative switch counts along c-rays

Notes
-----
- For serious experiments, increase precision aggressively.
- Near threshold, double precision roots are not reliable.
- This script is designed to be edited and extended.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import mpmath as mp
import numpy as np


# -----------------------------
# Xi-function and coefficient extraction
# -----------------------------

def Xi(z: mp.mpf | mp.mpc) -> mp.mpc:
    """Xi(z) = xi(1/2 + i z)."""
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def xi_gammas(max_index: int, dps: int = 100) -> list[mp.mpf]:
    """
    Compute gamma(0),...,gamma(max_index) from the Taylor series
        Xi(z) = sum a_k z^k,
    where
        a_{2m} = (-1)^m gamma(m)/(2m)!.

    Warning:
        This gets expensive quickly. Increase max_index in stages.
    """
    if max_index < 0:
        raise ValueError("max_index must be nonnegative")
    mp.mp.dps = dps
    taylor = mp.taylor(Xi, 0, 2 * max_index)
    gammas: list[mp.mpf] = []
    for m in range(max_index + 1):
        a_2m = mp.mpf(taylor[2 * m])
        gamma_m = ((-1) ** m) * a_2m * mp.factorial(2 * m)
        gammas.append(mp.re(gamma_m))
    return gammas


# -----------------------------
# Jensen polynomials and observables
# -----------------------------

def threshold_degree(n: int, c: float) -> int:
    """d = floor(c * n^(3/2) / sqrt(log n))."""
    if n < 3:
        raise ValueError("n must be at least 3")
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def c_nd(n: int, d: int) -> float:
    """Finite-n dimensionless degree parameter."""
    return d * math.sqrt(math.log(n)) / (n ** 1.5)


def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    """Ascending coefficients of J_{d,n}(X)."""
    if n < 0 or d < 0:
        raise ValueError("n and d must be nonnegative")
    if n + d >= len(gammas):
        raise ValueError(f"Need gamma coefficients through index {n+d}")
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending: list[mp.mpf]) -> np.ndarray:
    """Fast root finder for moderate exploratory runs."""
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def roots_mpmath(coeffs_ascending: list[mp.mpf], maxsteps: int = 100, cleanup: bool = True) -> list[mp.mpc]:
    """
    Higher-precision root finder.
    Coefficients must be given in descending order for mp.polyroots.
    """
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    return mp.polyroots(desc, maxsteps=maxsteps, cleanup=cleanup)


def count_real_roots(roots: Iterable[complex], tol: float = 1e-8) -> int:
    return sum(abs(z.imag) <= tol for z in roots)


def endpoint_state_proxy(roots: Iterable[complex], tol: float = 1e-8) -> str:
    """
    Basic proxy:
      '2'   -> all roots real
      '0'   -> at least one complex-conjugate pair present
      'amb' -> reserved for a custom high-precision transition classifier
    """
    roots = list(roots)
    real_count = count_real_roots(roots, tol=tol)
    if real_count == len(roots):
        return "2"
    return "0"


def defect_location_proxy(roots: Iterable[complex], tol: float = 1e-8) -> str:
    """
    Heuristic endpoint-vs-bulk label:
    among nonreal roots, look at the one with smallest |Im| and compare its real
    part with the most negative real root location. This is only a proxy.
    """
    roots = np.array(list(roots), dtype=np.complex128)
    nonreal = roots[np.abs(roots.imag) > tol]
    if len(nonreal) == 0:
        return "none"
    candidate = nonreal[np.argmin(np.abs(nonreal.imag))]
    if np.isclose(candidate.real, np.min(roots.real), atol=1e-8):
        return "endpoint_like"
    return "bulk_like"


@dataclass
class ScanRow:
    c: float
    n: int
    d: int
    c_nd: float
    real_root_deficit: int
    endpoint_state: str
    defect_location: str


def scan_ray(
    gammas: list[mp.mpf],
    c: float,
    n_values: Iterable[int],
    real_tol: float = 1e-8,
    root_method: str = "numpy",
) -> list[ScanRow]:
    rows: list[ScanRow] = []
    last_state: str | None = None
    switches = 0

    for n in n_values:
        d = threshold_degree(n, c)
        if d <= 0 or n + d >= len(gammas):
            continue

        coeffs = jensen_coeffs(gammas, n, d)

        if root_method == "mpmath":
            roots = roots_mpmath(coeffs)
        else:
            roots = roots_numpy(coeffs)

        state = endpoint_state_proxy(roots, tol=real_tol)
        if last_state is not None and state != "amb" and last_state != "amb" and state != last_state:
            switches += 1
        if state != "amb":
            last_state = state

        real_count = count_real_roots(roots, tol=real_tol)
        deficit = d - real_count

        rows.append(
            ScanRow(
                c=c,
                n=n,
                d=d,
                c_nd=c_nd(n, d),
                real_root_deficit=deficit,
                endpoint_state=state,
                defect_location=defect_location_proxy(roots, tol=real_tol),
            )
        )
    return rows


def write_rows_csv(rows: list[ScanRow], path: str | Path) -> None:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["c", "n", "d", "c_nd", "real_root_deficit", "endpoint_state", "defect_location"]
        )
        for r in rows:
            writer.writerow(
                [r.c, r.n, r.d, r.c_nd, r.real_root_deficit, r.endpoint_state, r.defect_location]
            )


# -----------------------------
# Theory-facing helper functions
# -----------------------------

def threshold_constant() -> float:
    return 1 / math.sqrt(math.pi)


def alpha_of_c(c: float) -> float:
    if c <= threshold_constant():
        raise ValueError("alpha(c) is only defined for supercritical c > 1/sqrt(pi)")
    kappa = math.log(c * math.sqrt(math.pi))
    return (4 * c / 3) * (kappa ** 1.5)


def n0_scale(c: float) -> float:
    """Heuristic first-defect scale."""
    a = alpha_of_c(c)
    return (a ** (-2 / 3)) * (math.log(1 / a) ** (4 / 3))


def Nc_scale(c: float) -> float:
    """Heuristic fast-sampling onset scale."""
    a = alpha_of_c(c)
    return (a ** (-2)) * (math.log(1 / a) ** 4)


# -----------------------------
# Example main
# -----------------------------

def main() -> None:
    # Adjust these for your run
    dps = 100
    max_gamma_index = 24
    c_values = [0.50, 0.54, 0.56, 0.57, 0.60, 0.70]
    n_values = range(3, 15)
    out_csv = Path(__file__).with_name("xi_jensen_scan.csv")
    root_method = "numpy"  # "numpy" for speed, "mpmath" for high-precision checks

    print("Threshold constant 1/sqrt(pi) =", threshold_constant())
    print("Computing Xi Taylor/Jensen coefficients...")
    gammas = xi_gammas(max_gamma_index, dps=dps)

    all_rows: list[ScanRow] = []
    for c in c_values:
        rows = scan_ray(gammas, c, n_values, root_method=root_method)
        all_rows.extend(rows)
        if c > threshold_constant():
            print(
                f"c={c:.3f}  alpha(c)={alpha_of_c(c):.6g}  "
                f"n0~{n0_scale(c):.6g}  Nc~{Nc_scale(c):.6g}  rows={len(rows)}"
            )
        else:
            print(f"c={c:.3f}  rows={len(rows)}")

    write_rows_csv(all_rows, out_csv)
    print(f"Wrote {out_csv.resolve()}")


if __name__ == "__main__":
    main()
