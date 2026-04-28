#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import time
from pathlib import Path

import mpmath as mp
import numpy as np


def Xi(z: mp.mpf | mp.mpc) -> mp.mpc:
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def xi_gammas_derivative(max_index: int, dps: int) -> list[mp.mpf]:
    mp.mp.dps = dps
    taylor = mp.taylor(Xi, 0, 2 * max_index)
    out = []
    for m in range(max_index + 1):
        a_2m = mp.mpf(taylor[2 * m])
        out.append(mp.re(((-1) ** m) * a_2m * mp.factorial(2 * m)))
    return out


def xi_gammas_contour(max_index: int, dps: int, radius: float, N: int) -> list[mp.mpf]:
    mp.mp.dps = dps
    vals = []
    for k in range(N):
        theta = 2 * mp.pi * k / N
        z = radius * mp.e ** (1j * theta)
        vals.append(Xi(z))
    out = []
    for m in range(max_index + 1):
        idx = 2 * m
        s = mp.mpc("0")
        for k, fk in enumerate(vals):
            theta = 2 * mp.pi * k / N
            s += fk * mp.e ** (-1j * idx * theta)
        a_idx = s / (N * (radius ** idx))
        out.append(mp.re(((-1) ** m) * mp.factorial(2 * m) * a_idx))
    return out


def rel_err(x: mp.mpf, y: mp.mpf) -> float:
    denom = max(1.0, float(abs(x)), float(abs(y)))
    return float(abs(x - y) / denom)


def threshold_degree(n: int, c: float) -> int:
    return int(math.floor(c * (n ** 1.5) / math.sqrt(math.log(n))))


def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_numpy(coeffs_ascending: list[mp.mpf]) -> np.ndarray:
    desc = np.array([complex(c) for c in reversed(coeffs_ascending)], dtype=np.complex128)
    return np.roots(desc)


def root_scale(z: complex) -> float:
    return max(1.0, abs(z), abs(z.real), abs(z.imag))


def is_nearly_real(z: complex, rtol: float = 1e-8, atol: float = 1e-12) -> bool:
    return abs(z.imag) <= atol + rtol * root_scale(z)


def count_real_roots(roots, rtol: float = 1e-8, atol: float = 1e-12) -> int:
    return sum(is_nearly_real(complex(z), rtol=rtol, atol=atol) for z in roots)


def deficit_profile(gammas: list[mp.mpf], c: float, n_start: int, n_stop: int) -> list[tuple[int, int, int]]:
    out = []
    for n in range(n_start, n_stop + 1):
        d = threshold_degree(n, c)
        if n + d >= len(gammas):
            continue
        coeffs = jensen_coeffs(gammas, n, d)
        roots = roots_numpy(coeffs)
        deficit = d - count_real_roots(roots)
        out.append((n, d, int(deficit)))
    return out


def main():
    out_csv = Path("xi_jensen_contour_stress_light_results.csv")
    out_summary = Path("xi_jensen_contour_stress_light_summary.txt")

    max_index = 12
    baseline_dps = 35
    c = 0.70
    n_start, n_stop = 8, 9

    radii = [0.60, 0.75, 0.90]
    Ns = [128, 256]
    contour_dps_values = [25, 35]

    t0 = time.perf_counter()
    gd = xi_gammas_derivative(max_index=max_index, dps=baseline_dps)
    t1 = time.perf_counter()
    baseline_time = t1 - t0
    baseline_profile = deficit_profile(gd, c=c, n_start=n_start, n_stop=n_stop)

    rows = []
    for radius in radii:
        for N in Ns:
            for contour_dps in contour_dps_values:
                t2 = time.perf_counter()
                gc = xi_gammas_contour(max_index=max_index, dps=contour_dps, radius=radius, N=N)
                t3 = time.perf_counter()

                errs = [rel_err(x, y) for x, y in zip(gd, gc)]
                profile = deficit_profile(gc, c=c, n_start=n_start, n_stop=n_stop)

                rows.append({
                    "max_index": max_index,
                    "baseline_dps": baseline_dps,
                    "baseline_time_sec": baseline_time,
                    "contour_dps": contour_dps,
                    "radius": radius,
                    "N": N,
                    "contour_time_sec": t3 - t2,
                    "speedup_vs_derivative": baseline_time / max(t3 - t2, 1e-12),
                    "gamma_max_relerr": max(errs),
                    "gamma_mean_relerr": sum(errs) / len(errs),
                    "baseline_profile": str(baseline_profile),
                    "contour_profile": str(profile),
                    "profile_match": int(profile == baseline_profile),
                })

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    ranked = sorted(
        rows,
        key=lambda r: (
            0 if r["profile_match"] else 1,
            r["gamma_max_relerr"],
            -r["speedup_vs_derivative"],
        ),
    )

    lines = []
    lines.append("Light contour stress harness summary")
    lines.append(f"baseline derivative time: {baseline_time:.6f}s")
    lines.append(f"baseline profile: {baseline_profile}")
    lines.append("")
    lines.append("All configurations:")
    for r in ranked:
        lines.append(
            f"dps={r['contour_dps']}, radius={r['radius']}, N={r['N']}: "
            f"max_relerr={r['gamma_max_relerr']:.3e}, "
            f"mean_relerr={r['gamma_mean_relerr']:.3e}, "
            f"profile_match={r['profile_match']}, "
            f"speedup={r['speedup_vs_derivative']:.2f}x, "
            f"profile={r['contour_profile']}"
        )

    out_summary.write_text("\\n".join(lines), encoding="utf-8")
    print("\\n".join(lines))
    print(f"\\nWrote {out_csv.resolve()}")
    print(f"Wrote {out_summary.resolve()}")


if __name__ == "__main__":
    main()
