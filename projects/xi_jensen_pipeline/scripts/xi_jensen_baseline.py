"""
xi_jensen_baseline.py

Unmodified copy of the client's original script, preserved verbatim for
before/after comparison. Do not edit.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import mpmath as mp
import numpy as np


def Xi(z):
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def xi_gammas(max_index: int, dps: int = 100) -> list:
    if max_index < 0:
        raise ValueError("max_index must be nonnegative")
    mp.mp.dps = dps
    taylor = mp.taylor(Xi, 0, 2 * max_index)
    gammas = []
    for m in range(max_index + 1):
        a_2m = mp.mpf(taylor[2 * m])
        gamma_m = ((-1) ** m) * a_2m * mp.factorial(2 * m)
        gammas.append(mp.re(gamma_m))
    return gammas


def threshold_degree(n: int, c: float) -> int:
    if n < 3:
        raise ValueError("n must be at least 3")
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def c_nd(n: int, d: int) -> float:
    return d * math.sqrt(math.log(n)) / (n ** 1.5)


def jensen_coeffs(gammas, n: int, d: int):
    if n < 0 or d < 0:
        raise ValueError("n and d must be nonnegative")
    if n + d >= len(gammas):
        raise ValueError(f"Need gamma coefficients through index {n+d}")
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def roots_mpmath(coeffs_ascending, maxsteps: int = 100, cleanup: bool = True):
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    return mp.polyroots(desc, maxsteps=maxsteps, cleanup=cleanup)


def count_real_roots(roots, tol: float = 1e-8) -> int:
    return sum(abs(z.imag) <= tol for z in roots)


def endpoint_state_proxy(roots, tol: float = 1e-8) -> str:
    roots = list(roots)
    real_count = count_real_roots(roots, tol=tol)
    if real_count == len(roots):
        return "2"
    return "0"


def defect_location_proxy(roots, tol: float = 1e-8) -> str:
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


def scan_ray(gammas, c: float, n_values, real_tol: float = 1e-8, root_method: str = "numpy"):
    rows = []
    last_state = None
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
                c=c, n=n, d=d, c_nd=c_nd(n, d),
                real_root_deficit=deficit,
                endpoint_state=state,
                defect_location=defect_location_proxy(roots, tol=real_tol),
            )
        )
    return rows


def write_rows_csv(rows, path) -> None:
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


def run(dps: int, max_gamma_index: int, c_values, n_values, out_csv, root_method="numpy"):
    mp.mp.dps = dps
    gammas = xi_gammas(max_gamma_index, dps=dps)
    all_rows = []
    for c in c_values:
        all_rows.extend(scan_ray(gammas, c, n_values, root_method=root_method))
    write_rows_csv(all_rows, out_csv)
    return gammas, all_rows


if __name__ == "__main__":
    run(
        dps=100,
        max_gamma_index=24,
        c_values=[0.50, 0.54, 0.56, 0.57, 0.60, 0.70],
        n_values=range(3, 15),
        out_csv=Path("xi_jensen_scan_baseline.csv"),
        root_method="numpy",
    )
