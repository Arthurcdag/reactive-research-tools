#!/usr/bin/env python3
"""
xi_jensen_phase_diagram_fft.py

Faster prototype for Xi–Jensen scans.

Key idea
--------
Avoid high-order differentiation of Xi(z) at z=0.
Instead, recover Taylor coefficients from Xi sampled on a circle:

    a_m = (1/N) * sum_{k=0}^{N-1} Xi(R * exp(2πik/N)) * exp(-2πi m k / N) / R^m

Then
    gamma(m) = (-1)^m * (2m)! * a_{2m}

This uses a discrete Cauchy / DFT coefficient extraction, which is often much
faster than repeated automatic differentiation for moderate coefficient ranges.

This is a research prototype, not a certified validated production routine.
You should compare a few low-order coefficients against the original derivative
method before relying on large runs.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import mpmath as mp
import numpy as np


def Xi(z: mp.mpf | mp.mpc) -> mp.mpc:
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


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


def threshold_degree(n: int, c: float) -> int:
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def c_nd(n: int, d: int) -> float:
    return d * math.sqrt(math.log(n)) / (n ** 1.5)


def xi_gammas_fft(max_index: int, dps: int = 80, radius: float = 0.75, N: int | None = None) -> list[mp.mpf]:
    """
    Recover gamma(0),...,gamma(max_index) from Taylor coefficients of Xi
    using a circular DFT / Cauchy coefficient extraction.
    """
    mp.mp.dps = dps
    M = 2 * max_index
    if N is None:
        N = 8 * (M + 1)
        p = 1
        while p < N:
            p *= 2
        N = p

    vals = []
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


def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    if n + d >= len(gammas):
        raise ValueError(f"Need gamma coefficients through index {n+d}")
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


@dataclass
class ScanRow:
    c: float
    n: int
    d: int
    c_nd: float
    real_root_deficit: int
    endpoint_state: str
    defect_location: str


def scan_ray(gammas, c: float, n_values, real_tol: float = 1e-8) -> list[ScanRow]:
    rows = []
    for n in n_values:
        d = threshold_degree(n, c)
        if d <= 0 or n + d >= len(gammas):
            continue
        coeffs = jensen_coeffs(gammas, n, d)
        roots = roots_numpy(coeffs)
        real_count = count_real_roots(roots, tol=real_tol)
        rows.append(
            ScanRow(
                c=c,
                n=n,
                d=d,
                c_nd=c_nd(n, d),
                real_root_deficit=int(d - real_count),
                endpoint_state=endpoint_state_proxy(roots, tol=real_tol),
                defect_location=defect_location_proxy(roots, tol=real_tol),
            )
        )
    return rows


def write_rows_csv(rows: list[ScanRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["c", "n", "d", "c_nd", "real_root_deficit", "endpoint_state", "defect_location"])
        for r in rows:
            w.writerow([r.c, r.n, r.d, r.c_nd, r.real_root_deficit, r.endpoint_state, r.defect_location])


PRESETS = {
    "c070_fast": {
        "c_values": [0.70],
        "n_start": 8,
        "n_stop": 60,
        "dps": 70,
        "max_gamma_index": 90,
        "radius": 0.75,
        "N": 1024,
        "output_name": "xi_jensen_fft_c070.csv",
    },
    "c060_medium": {
        "c_values": [0.60],
        "n_start": 20,
        "n_stop": 180,
        "dps": 80,
        "max_gamma_index": 260,
        "radius": 0.75,
        "N": 4096,
        "output_name": "xi_jensen_fft_c060.csv",
    },
}


def parse_args():
    p = argparse.ArgumentParser(description="FFT/Cauchy Xi–Jensen scanner")
    p.add_argument("--preset", choices=sorted(PRESETS.keys()))
    p.add_argument("--custom-c", type=float)
    p.add_argument("--n-start", type=int)
    p.add_argument("--n-stop", type=int)
    p.add_argument("--dps", type=int)
    p.add_argument("--max-gamma-index", type=int)
    p.add_argument("--radius", type=float)
    p.add_argument("--N", type=int)
    p.add_argument("--output-name", type=str)
    return p.parse_args()


def config_from_args(args):
    if args.preset:
        cfg = PRESETS[args.preset].copy()
    elif args.custom_c is not None:
        cfg = {
            "c_values": [args.custom_c],
            "n_start": args.n_start if args.n_start is not None else 8,
            "n_stop": args.n_stop if args.n_stop is not None else 60,
            "dps": args.dps if args.dps is not None else 70,
            "max_gamma_index": args.max_gamma_index if args.max_gamma_index is not None else 90,
            "radius": args.radius if args.radius is not None else 0.75,
            "N": args.N if args.N is not None else 1024,
            "output_name": args.output_name if args.output_name is not None else "xi_jensen_fft_custom.csv",
        }
    else:
        raise SystemExit("Use --preset or --custom-c")

    for key in ["n_start", "n_stop", "dps", "max_gamma_index", "radius", "N", "output_name"]:
        attr = key.replace("-", "_")
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

    all_rows = []
    n_values = range(cfg["n_start"], cfg["n_stop"] + 1)
    for c in cfg["c_values"]:
        rows = scan_ray(gammas, c, n_values)
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
