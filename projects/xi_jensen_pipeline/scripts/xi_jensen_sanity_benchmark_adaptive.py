#!/usr/bin/env python3
"""
xi_jensen_sanity_benchmark_adaptive.py

Adaptive sanity + benchmark helper for the Xi–Jensen workflow.

What is new
-----------
Unlike the earlier sanity benchmark, this version automatically computes enough
gamma coefficients for the requested n-window and degree rule, so the root
comparison actually runs.

It answers:
1. Do derivative-based and contour-based gamma tables agree on low orders?
2. Is contour extraction faster on a matched small test?
3. On an actual overlap window, do numpy roots and scaled polyroots agree?
"""

from __future__ import annotations

import argparse
import math
import time

import mpmath as mp
import numpy as np


def Xi(z: mp.mpf | mp.mpc) -> mp.mpc:
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def threshold_degree(n: int, c: float) -> int:
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def required_max_index(c: float | None, fixed_d: int | None, n_start: int, n_stop: int, safety: int = 2) -> int:
    if (c is None) == (fixed_d is None):
        raise ValueError("Provide exactly one of c or fixed_d")
    max_need = 0
    for n in range(n_start, n_stop + 1):
        d = threshold_degree(n, c) if c is not None else int(fixed_d)
        max_need = max(max_need, n + d)
    return max_need + safety


def xi_gammas_derivative(max_index: int, dps: int = 50) -> list[mp.mpf]:
    mp.mp.dps = dps
    taylor = mp.taylor(Xi, 0, 2 * max_index)
    gammas = []
    for m in range(max_index + 1):
        a_2m = mp.mpf(taylor[2 * m])
        gamma_m = ((-1) ** m) * a_2m * mp.factorial(2 * m)
        gammas.append(mp.re(gamma_m))
    return gammas


def xi_gammas_contour(max_index: int, dps: int = 50, radius: float = 0.75, N: int | None = None) -> list[mp.mpf]:
    mp.mp.dps = dps
    max_taylor_index = 2 * max_index
    if N is None:
        N = 8 * (max_taylor_index + 1)
        p = 1
        while p < N:
            p *= 2
        N = p

    vals = []
    for k in range(N):
        theta = 2 * mp.pi * k / N
        z = radius * mp.e ** (1j * theta)
        vals.append(Xi(z))

    gammas = []
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
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending: list[mp.mpf]) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def roots_polyroots_scaled(coeffs_ascending: list[mp.mpf]) -> list[mp.mpc]:
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    while len(desc) > 1 and abs(desc[0]) == 0:
        desc = desc[1:]

    lead = desc[0]
    monic = [z / lead for z in desc]
    deg = len(monic) - 1
    if deg <= 0:
        return []

    B = 1 + max(abs(z) for z in monic[1:])
    scales = [mp.sqrt(B), B, mp.nthroot(B, 3), mp.mpf("1")]

    last_err = None
    for s in scales:
        scaled = [monic[k] * (s ** (deg - k)) for k in range(deg + 1)]
        scaled = [z / scaled[0] for z in scaled]
        attempts = [
            {"maxsteps": 200, "cleanup": False, "extraprec": 50},
            {"maxsteps": 500, "cleanup": False, "extraprec": 80},
        ]
        for opts in attempts:
            try:
                roots_y = mp.polyroots(scaled, **opts)
                return [s * r for r in roots_y]
            except Exception as e:
                last_err = e
    raise last_err


def rel_err(x: mp.mpf, y: mp.mpf) -> float:
    denom = max(1.0, float(abs(x)), float(abs(y)))
    return float(abs(x - y) / denom)


def root_scale(z: complex) -> float:
    return max(1.0, abs(z), abs(z.real), abs(z.imag))


def is_nearly_real(z: complex, rtol: float = 1e-8, atol: float = 1e-12) -> bool:
    return abs(z.imag) <= atol + rtol * root_scale(z)


def count_real_roots(roots, rtol: float = 1e-8, atol: float = 1e-12) -> int:
    return sum(is_nearly_real(complex(z), rtol=rtol, atol=atol) for z in roots)


def defect_location_proxy(roots, rtol: float = 1e-6, atol: float = 1e-12) -> str:
    roots = np.array([complex(z) for z in roots], dtype=np.complex128)
    nonreal = roots[[not is_nearly_real(z, rtol=rtol, atol=atol) for z in roots]]
    if len(nonreal) == 0:
        return "none"
    candidate = nonreal[np.argmin(np.abs(nonreal.imag))]
    xmin = float(np.min(roots.real))
    xmax = float(np.max(roots.real))
    scale = max(1.0, abs(xmin), abs(xmax), abs(candidate.real))
    if abs(candidate.real - xmin) <= atol + rtol * scale or abs(candidate.real - xmax) <= atol + rtol * scale:
        return "endpoint_like"
    return "bulk_like"


def benchmark_extractors(max_index: int, dps: int, radius: float, N: int):
    print("=== gamma extractor benchmark ===")
    t0 = time.perf_counter()
    gd = xi_gammas_derivative(max_index=max_index, dps=dps)
    t1 = time.perf_counter()
    gc = xi_gammas_contour(max_index=max_index, dps=dps, radius=radius, N=N)
    t2 = time.perf_counter()

    errs = [rel_err(x, y) for x, y in zip(gd, gc)]
    print(f"max_index used:  {max_index}")
    print(f"derivative time: {t1 - t0:.3f}s")
    print(f"contour time:    {t2 - t1:.3f}s")
    print(f"speedup:         {(t1 - t0)/(t2 - t1):.2f}x")
    print(f"max relative gamma difference:  {max(errs):.3e}")
    print(f"mean relative gamma difference: {sum(errs)/len(errs):.3e}")
    print()
    return gc


def benchmark_roots(gammas: list[mp.mpf], c: float | None, fixed_d: int | None, n_start: int, n_stop: int):
    print("=== root-method comparison ===")
    comparisons = 0
    deficit_agree = 0
    loc_agree = 0

    for n in range(n_start, n_stop + 1):
        d = threshold_degree(n, c) if c is not None else int(fixed_d)
        if d <= 0 or n + d >= len(gammas):
            continue
        coeffs = jensen_coeffs(gammas, n, d)

        try:
            rn = roots_numpy(coeffs)
            dn = d - count_real_roots(rn)
            ln = defect_location_proxy(rn)
        except Exception as e:
            dn = None
            ln = f"numpy_error:{type(e).__name__}"

        try:
            rp = roots_polyroots_scaled(coeffs)
            dp = d - count_real_roots(rp)
            lp = defect_location_proxy(rp)
        except Exception as e:
            dp = None
            lp = f"poly_error:{type(e).__name__}"

        comparisons += 1
        deficit_agree += int(dn == dp)
        loc_agree += int(ln == lp)

        print(
            f"n={n:2d} d={d:2d} | "
            f"numpy deficit={str(dn):>4} loc={ln:<15} | "
            f"poly deficit={str(dp):>4} loc={lp}"
        )

    print()
    if comparisons:
        print(f"deficit agreement: {deficit_agree}/{comparisons}")
        print(f"location agreement: {loc_agree}/{comparisons}")
    else:
        print("No comparable root rows were generated.")


def parse_args():
    p = argparse.ArgumentParser(description="Adaptive Xi–Jensen sanity benchmark")
    p.add_argument("--dps", type=int, default=40)
    p.add_argument("--radius", type=float, default=0.75)
    p.add_argument("--N", type=int, default=512)
    p.add_argument("--c", type=float, default=0.70)
    p.add_argument("--fixed-d", type=int)
    p.add_argument("--n-start", type=int, default=8)
    p.add_argument("--n-stop", type=int, default=12)
    return p.parse_args()


def main():
    args = parse_args()
    c = args.c if args.fixed_d is None else None
    fixed_d = args.fixed_d
    max_index = required_max_index(c=c, fixed_d=fixed_d, n_start=args.n_start, n_stop=args.n_stop)

    gc = benchmark_extractors(
        max_index=max_index,
        dps=args.dps,
        radius=args.radius,
        N=args.N,
    )
    benchmark_roots(gc, c=c, fixed_d=fixed_d, n_start=args.n_start, n_stop=args.n_stop)


if __name__ == "__main__":
    main()
