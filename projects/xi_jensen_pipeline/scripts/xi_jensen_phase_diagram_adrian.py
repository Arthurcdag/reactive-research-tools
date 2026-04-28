#!/usr/bin/env python3
"""
xi_jensen_phase_diagram_adrian.py

A faster, more numerically sane Xi–Jensen scanner.

What's changed from the earlier versions
----------------------------------------
1. Coefficients gamma(n) are extracted by circle sampling + discrete Cauchy/DFT,
   instead of repeated high-order differentiation.
2. Root classification uses a RELATIVE tolerance, not just an absolute one.
3. The theory-driven degree choice
       d = floor(c * n^(3/2) / sqrt(log n))
   is kept, but can be turned off by giving an explicit fixed d.

This is the "Adrian version":
- faster
- scale-aware
- less brittle numerically
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
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def xi_gammas_fft(max_index: int, dps: int = 80, radius: float = 0.75, N: int | None = None) -> list[mp.mpf]:
    """
    Recover gamma(0),...,gamma(max_index) from Taylor coefficients of Xi
    using circular sampling + discrete Cauchy/DFT extraction.

    If Xi(z) = sum a_m z^m, then
        a_m ≈ (1/N) sum_k Xi(R e^{2πik/N}) e^{-2π i m k / N} / R^m
    and
        gamma(m) = (-1)^m (2m)! a_{2m}
    """
    if max_index < 0:
        raise ValueError("max_index must be nonnegative")

    mp.mp.dps = dps
    max_taylor_index = 2 * max_index

    if N is None:
        N = 8 * (max_taylor_index + 1)
        p = 1
        while p < N:
            p *= 2
        N = p

    vals: list[mp.mpc] = []
    for k in range(N):
        theta = 2 * mp.pi * k / N
        z = radius * mp.e ** (1j * theta)
        vals.append(Xi(z))

    gammas: list[mp.mpf] = []
    for m in range(max_index + 1):
        idx = 2 * m
        s = mp.mpc("0")
        for k, fk in enumerate(vals):
            theta = 2 * mp.pi * k / N
            s += fk * mp.e ** (-1j * idx * theta)
        a_idx = s / (N * (radius ** idx))
        gamma_m = ((-1) ** m) * mp.factorial(2 * m) * a_idx
        gammas.append(mp.re(gamma_m))

    return gammas


# -----------------------------
# Theory-facing helper functions
# -----------------------------

def threshold_constant() -> float:
    return 1.0 / math.sqrt(math.pi)


def alpha_of_c(c: float) -> float:
    if c <= threshold_constant():
        raise ValueError("alpha(c) only defined for c > 1/sqrt(pi)")
    kappa = math.log(c * math.sqrt(math.pi))
    return (4.0 * c / 3.0) * (kappa ** 1.5)


def n0_scale(c: float) -> float:
    a = alpha_of_c(c)
    return (a ** (-2.0 / 3.0)) * (math.log(1.0 / a) ** (4.0 / 3.0))


def Nc_scale(c: float) -> float:
    a = alpha_of_c(c)
    return (a ** (-2.0)) * (math.log(1.0 / a) ** 4.0)


def threshold_degree(n: int, c: float) -> int:
    if n < 3:
        raise ValueError("n must be at least 3")
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def c_nd(n: int, d: int) -> float:
    return d * math.sqrt(math.log(n)) / (n ** 1.5)


# -----------------------------
# Jensen polynomials
# -----------------------------

def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    if n < 0 or d < 0:
        raise ValueError("n and d must be nonnegative")
    if n + d >= len(gammas):
        raise ValueError(f"Need gamma coefficients through index {n + d}")
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending: list[mp.mpf]) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


# -----------------------------
# Relative-tolerance numerics
# -----------------------------

def root_scale(z: complex) -> float:
    return max(1.0, abs(z), abs(z.real), abs(z.imag))


def is_nearly_real(z: complex, rtol: float = 1e-8, atol: float = 1e-12) -> bool:
    return abs(z.imag) <= atol + rtol * root_scale(z)


def approx_equal(x: float, y: float, rtol: float = 1e-6, atol: float = 1e-12) -> bool:
    scale = max(1.0, abs(x), abs(y))
    return abs(x - y) <= atol + rtol * scale


def count_real_roots(roots: Iterable[complex], rtol: float = 1e-8, atol: float = 1e-12) -> int:
    return sum(is_nearly_real(z, rtol=rtol, atol=atol) for z in roots)


def endpoint_state_proxy(roots: Iterable[complex], rtol: float = 1e-8, atol: float = 1e-12) -> str:
    roots = list(roots)
    real_count = count_real_roots(roots, rtol=rtol, atol=atol)
    if real_count == len(roots):
        return "2"
    # Reserved for future transition-band logic
    return "0"


def defect_location_proxy(roots: Iterable[complex], rtol: float = 1e-6, atol: float = 1e-12) -> str:
    roots = np.array(list(roots), dtype=np.complex128)
    nonreal = roots[[not is_nearly_real(z, rtol=rtol, atol=atol) for z in roots]]
    if len(nonreal) == 0:
        return "none"

    candidate = nonreal[np.argmin(np.abs(nonreal.imag))]
    xmin = float(np.min(roots.real))
    xmax = float(np.max(roots.real))

    if approx_equal(float(candidate.real), xmin, rtol=rtol, atol=atol) or approx_equal(
        float(candidate.real), xmax, rtol=rtol, atol=atol
    ):
        return "endpoint_like"
    return "bulk_like"


# -----------------------------
# Scan rows
# -----------------------------

@dataclass
class ScanRow:
    mode: str
    c: float | None
    fixed_d: int | None
    n: int
    d: int
    c_nd: float
    real_root_deficit: int
    endpoint_state: str
    defect_location: str
    max_rel_imag: float


def max_relative_imag(roots: Iterable[complex]) -> float:
    vals = []
    for z in roots:
        vals.append(abs(z.imag) / root_scale(z))
    return float(max(vals)) if vals else 0.0


def scan_ray(
    gammas: list[mp.mpf],
    n_values: Iterable[int],
    *,
    c: float | None = None,
    fixed_d: int | None = None,
    real_rtol: float = 1e-8,
    real_atol: float = 1e-12,
) -> list[ScanRow]:
    if (c is None) == (fixed_d is None):
        raise ValueError("Provide exactly one of c or fixed_d")

    rows: list[ScanRow] = []
    mode = "threshold_ray" if c is not None else "fixed_d"

    for n in n_values:
        d = threshold_degree(n, c) if c is not None else int(fixed_d)
        if d <= 0 or n + d >= len(gammas):
            continue

        coeffs = jensen_coeffs(gammas, n, d)
        roots = roots_numpy(coeffs)

        real_count = count_real_roots(roots, rtol=real_rtol, atol=real_atol)
        rows.append(
            ScanRow(
                mode=mode,
                c=c,
                fixed_d=fixed_d,
                n=n,
                d=d,
                c_nd=c_nd(n, d),
                real_root_deficit=int(d - real_count),
                endpoint_state=endpoint_state_proxy(roots, rtol=real_rtol, atol=real_atol),
                defect_location=defect_location_proxy(roots, rtol=1e-5, atol=real_atol),
                max_rel_imag=max_relative_imag(roots),
            )
        )

    return rows


def write_rows_csv(rows: list[ScanRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "mode",
                "c",
                "fixed_d",
                "n",
                "d",
                "c_nd",
                "real_root_deficit",
                "endpoint_state",
                "defect_location",
                "max_rel_imag",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.mode,
                    r.c,
                    r.fixed_d,
                    r.n,
                    r.d,
                    r.c_nd,
                    r.real_root_deficit,
                    r.endpoint_state,
                    r.defect_location,
                    r.max_rel_imag,
                ]
            )


PRESETS = {
    "c070_fast": {
        "mode": "threshold_ray",
        "c": 0.70,
        "fixed_d": None,
        "n_start": 8,
        "n_stop": 60,
        "dps": 70,
        "max_gamma_index": 90,
        "radius": 0.75,
        "N": 1024,
        "real_rtol": 1e-8,
        "real_atol": 1e-12,
        "output_name": "xi_jensen_adrian_c070.csv",
    },
    "c060_medium": {
        "mode": "threshold_ray",
        "c": 0.60,
        "fixed_d": None,
        "n_start": 20,
        "n_stop": 180,
        "dps": 80,
        "max_gamma_index": 260,
        "radius": 0.75,
        "N": 4096,
        "real_rtol": 1e-8,
        "real_atol": 1e-12,
        "output_name": "xi_jensen_adrian_c060.csv",
    },
    "fixed_d_20_demo": {
        "mode": "fixed_d",
        "c": None,
        "fixed_d": 20,
        "n_start": 20,
        "n_stop": 80,
        "dps": 60,
        "max_gamma_index": 120,
        "radius": 0.75,
        "N": 2048,
        "real_rtol": 1e-8,
        "real_atol": 1e-12,
        "output_name": "xi_jensen_adrian_fixed_d20.csv",
    },
}


def parse_args():
    p = argparse.ArgumentParser(description="Fast relative-tolerance Xi–Jensen scanner")
    p.add_argument("--preset", choices=sorted(PRESETS.keys()))
    p.add_argument("--custom-c", type=float, help="Use theory ray d=floor(c n^(3/2)/sqrt(log n))")
    p.add_argument("--fixed-d", type=int, help="Use a fixed degree d instead of the theory ray")
    p.add_argument("--n-start", type=int)
    p.add_argument("--n-stop", type=int)
    p.add_argument("--dps", type=int)
    p.add_argument("--max-gamma-index", type=int)
    p.add_argument("--radius", type=float)
    p.add_argument("--N", type=int)
    p.add_argument("--real-rtol", type=float)
    p.add_argument("--real-atol", type=float)
    p.add_argument("--output-name", type=str)
    return p.parse_args()


def config_from_args(args):
    if args.preset:
        cfg = PRESETS[args.preset].copy()
    elif args.custom_c is not None or args.fixed_d is not None:
        if args.custom_c is not None and args.fixed_d is not None:
            raise SystemExit("Choose either --custom-c or --fixed-d, not both")
        cfg = {
            "mode": "threshold_ray" if args.custom_c is not None else "fixed_d",
            "c": args.custom_c,
            "fixed_d": args.fixed_d,
            "n_start": args.n_start if args.n_start is not None else 8,
            "n_stop": args.n_stop if args.n_stop is not None else 60,
            "dps": args.dps if args.dps is not None else 70,
            "max_gamma_index": args.max_gamma_index if args.max_gamma_index is not None else 90,
            "radius": args.radius if args.radius is not None else 0.75,
            "N": args.N if args.N is not None else 1024,
            "real_rtol": args.real_rtol if args.real_rtol is not None else 1e-8,
            "real_atol": args.real_atol if args.real_atol is not None else 1e-12,
            "output_name": args.output_name if args.output_name is not None else "xi_jensen_adrian_custom.csv",
        }
    else:
        raise SystemExit("Use --preset, --custom-c, or --fixed-d")

    # Optional overrides on top of a preset
    for key, attr in [
        ("n_start", "n_start"),
        ("n_stop", "n_stop"),
        ("dps", "dps"),
        ("max_gamma_index", "max_gamma_index"),
        ("radius", "radius"),
        ("N", "N"),
        ("real_rtol", "real_rtol"),
        ("real_atol", "real_atol"),
        ("output_name", "output_name"),
    ]:
        val = getattr(args, attr, None)
        if val is not None:
            cfg[key] = val

    return cfg


def main():
    args = parse_args()
    cfg = config_from_args(args)
    script_dir = Path(__file__).resolve().parent
    out_csv = script_dir / cfg["output_name"]

    print("Threshold constant 1/sqrt(pi) =", threshold_constant())
    print("Config:", cfg)
    print("Computing Xi Taylor/Jensen coefficients via circle sampling...")
    gammas = xi_gammas_fft(
        max_index=cfg["max_gamma_index"],
        dps=cfg["dps"],
        radius=cfg["radius"],
        N=cfg["N"],
    )

    n_values = range(cfg["n_start"], cfg["n_stop"] + 1)
    rows = scan_ray(
        gammas,
        n_values,
        c=cfg["c"],
        fixed_d=cfg["fixed_d"],
        real_rtol=cfg["real_rtol"],
        real_atol=cfg["real_atol"],
    )

    if cfg["c"] is not None and cfg["c"] > threshold_constant():
        c = cfg["c"]
        print(
            f"c={c:.3f}  alpha(c)={alpha_of_c(c):.8g}  "
            f"n0~{n0_scale(c):.6g}  Nc~{Nc_scale(c):.6g}  rows={len(rows)}"
        )
    else:
        print(f"rows={len(rows)}")

    write_rows_csv(rows, out_csv)
    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
