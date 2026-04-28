#!/usr/bin/env python3
"""
xi_jensen_phase_diagram_targeted.py

Updated targeted runner for Xi–Jensen threshold experiments.

Goals
-----
- Avoid repeated manual config edits
- Provide focused presets for the most relevant supercritical tests
- Write output next to the script
- Print theory-facing scales n0(c) and Nc(c)
- Keep the original observable pipeline

Examples
--------
Fast check for c = 0.70:
    python xi_jensen_phase_diagram_targeted.py --preset c070_fast

Moderate check for c = 0.60:
    python xi_jensen_phase_diagram_targeted.py --preset c060_medium

Custom run:
    python xi_jensen_phase_diagram_targeted.py --custom-c 0.70 --n-start 8 --n-stop 60 --dps 120 --max-gamma-index 80
"""

from __future__ import annotations

import argparse
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
    if n < 3:
        raise ValueError("n must be at least 3")
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def c_nd(n: int, d: int) -> float:
    return d * math.sqrt(math.log(n)) / (n ** 1.5)


def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    if n < 0 or d < 0:
        raise ValueError("n and d must be nonnegative")
    if n + d >= len(gammas):
        raise ValueError(f"Need gamma coefficients through index {n+d}")
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending: list[mp.mpf]) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def roots_mpmath(coeffs_ascending: list[mp.mpf], maxsteps: int = 100, cleanup: bool = True) -> list[mp.mpc]:
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    return mp.polyroots(desc, maxsteps=maxsteps, cleanup=cleanup)


def count_real_roots(roots: Iterable[complex], tol: float = 1e-8) -> int:
    return sum(abs(z.imag) <= tol for z in roots)


def endpoint_state_proxy(roots: Iterable[complex], tol: float = 1e-8) -> str:
    roots = list(roots)
    real_count = count_real_roots(roots, tol=tol)
    if real_count == len(roots):
        return "2"
    return "0"


def defect_location_proxy(roots: Iterable[complex], tol: float = 1e-8) -> str:
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
    for n in n_values:
        d = threshold_degree(n, c)
        if d <= 0 or n + d >= len(gammas):
            continue

        coeffs = jensen_coeffs(gammas, n, d)
        roots = roots_mpmath(coeffs) if root_method == "mpmath" else roots_numpy(coeffs)

        real_count = count_real_roots(roots, tol=real_tol)
        deficit = d - real_count
        state = endpoint_state_proxy(roots, tol=real_tol)

        rows.append(
            ScanRow(
                c=c,
                n=n,
                d=d,
                c_nd=c_nd(n, d),
                real_root_deficit=int(deficit),
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
    a = alpha_of_c(c)
    return (a ** (-2 / 3)) * (math.log(1 / a) ** (4 / 3))


def Nc_scale(c: float) -> float:
    a = alpha_of_c(c)
    return (a ** (-2)) * (math.log(1 / a) ** 4)


# -----------------------------
# Presets
# -----------------------------

PRESETS: dict[str, dict] = {
    "c070_fast": {
        "c_values": [0.70],
        "n_start": 8,
        "n_stop": 60,
        "dps": 120,
        "max_gamma_index": 80,
        "root_method": "numpy",
        "output_name": "xi_jensen_scan_c070.csv",
    },
    "c060_medium": {
        "c_values": [0.60],
        "n_start": 20,
        "n_stop": 180,
        "dps": 140,
        "max_gamma_index": 220,
        "root_method": "numpy",
        "output_name": "xi_jensen_scan_c060.csv",
    },
    "c057_heavy": {
        "c_values": [0.57],
        "n_start": 200,
        "n_stop": 1700,
        "dps": 180,
        "max_gamma_index": 1800,
        "root_method": "numpy",
        "output_name": "xi_jensen_scan_c057.csv",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Targeted Xi–Jensen threshold scanner")
    parser.add_argument("--preset", choices=sorted(PRESETS.keys()), help="Named preset run")
    parser.add_argument("--custom-c", type=float, help="Single custom c value")
    parser.add_argument("--n-start", type=int, help="Start of n range (inclusive)")
    parser.add_argument("--n-stop", type=int, help="Stop of n range (inclusive)")
    parser.add_argument("--dps", type=int, help="mpmath decimal precision")
    parser.add_argument("--max-gamma-index", type=int, help="Maximum gamma index to compute")
    parser.add_argument("--root-method", choices=["numpy", "mpmath"], help="Root solver")
    parser.add_argument("--output-name", type=str, help="CSV output file name")
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> dict:
    if args.preset:
        cfg = PRESETS[args.preset].copy()
    elif args.custom_c is not None:
        cfg = {
            "c_values": [args.custom_c],
            "n_start": args.n_start if args.n_start is not None else 8,
            "n_stop": args.n_stop if args.n_stop is not None else 60,
            "dps": args.dps if args.dps is not None else 120,
            "max_gamma_index": args.max_gamma_index if args.max_gamma_index is not None else 80,
            "root_method": args.root_method if args.root_method is not None else "numpy",
            "output_name": args.output_name if args.output_name is not None else "xi_jensen_scan_custom.csv",
        }
    else:
        raise SystemExit("Use --preset or --custom-c")

    # Allow selective overrides on top of a preset
    if args.n_start is not None:
        cfg["n_start"] = args.n_start
    if args.n_stop is not None:
        cfg["n_stop"] = args.n_stop
    if args.dps is not None:
        cfg["dps"] = args.dps
    if args.max_gamma_index is not None:
        cfg["max_gamma_index"] = args.max_gamma_index
    if args.root_method is not None:
        cfg["root_method"] = args.root_method
    if args.output_name is not None:
        cfg["output_name"] = args.output_name

    return cfg


def main() -> None:
    args = parse_args()
    cfg = config_from_args(args)

    script_dir = Path(__file__).resolve().parent
    out_csv = script_dir / cfg["output_name"]
    n_values = range(cfg["n_start"], cfg["n_stop"] + 1)

    print("Threshold constant 1/sqrt(pi) =", threshold_constant())
    print("Config:", cfg)
    print("Computing Xi Taylor/Jensen coefficients...")
    gammas = xi_gammas(cfg["max_gamma_index"], dps=cfg["dps"])

    all_rows: list[ScanRow] = []
    for c in cfg["c_values"]:
        rows = scan_ray(gammas, c, n_values, root_method=cfg["root_method"])
        all_rows.extend(rows)
        if c > threshold_constant():
            print(
                f"c={c:.3f}  alpha(c)={alpha_of_c(c):.8g}  "
                f"n0~{n0_scale(c):.6g}  Nc~{Nc_scale(c):.6g}  rows={len(rows)}"
            )
        else:
            print(f"c={c:.3f}  rows={len(rows)}")

    write_rows_csv(all_rows, out_csv)
    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
