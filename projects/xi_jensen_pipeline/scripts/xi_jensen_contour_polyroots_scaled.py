#!/usr/bin/env python3
"""
xi_jensen_contour_polyroots_scaled.py

Patched contour + polyroots Xi–Jensen scanner.

Main fix
--------
mpmath.polyroots often fails on the raw Jensen polynomial because the coefficient
scales are poor. This version rescales the polynomial before calling polyroots:

1. make the polynomial monic
2. estimate a root-scale using a Cauchy-style bound
3. solve in the scaled variable y where x = s*y
4. map the roots back to x

This makes polyroots much more stable on the moderate-degree validation runs.

Important note
--------------
This version is best used as a validation / confirmation runner, not as the
main broad scanner. For broad scans, the numpy-root versions are still faster.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import mpmath as mp
import numpy as np


def Xi(z: mp.mpf | mp.mpc) -> mp.mpc:
    s = mp.mpf("0.5") + 1j * z
    return mp.mpf("0.5") * s * (s - 1) * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)


def cache_key(max_index: int, dps: int, radius: float, N: int) -> str:
    payload = json.dumps(
        {"max_index": max_index, "dps": dps, "radius": radius, "N": N},
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def gamma_cache_paths(cache_dir: Path, *, max_index: int, dps: int, radius: float, N: int) -> tuple[Path, Path]:
    key = cache_key(max_index=max_index, dps=dps, radius=radius, N=N)
    return (
        cache_dir / f"xi_gamma_cache_{key}.json",
        cache_dir / f"xi_gamma_cache_{key}.npz",
    )


def xi_gammas_contour(max_index: int, dps: int = 80, radius: float = 0.75, N: int | None = None) -> list[mp.mpf]:
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


def save_gamma_cache(gammas: list[mp.mpf], json_path: Path, npz_path: Path, *, max_index: int, dps: int, radius: float, N: int) -> None:
    meta = {
        "max_index": max_index,
        "dps": dps,
        "radius": radius,
        "N": N,
        "count": len(gammas),
    }
    json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    arr = np.array([str(g) for g in gammas], dtype=object)
    np.savez_compressed(npz_path, gammas=arr)


def load_gamma_cache(json_path: Path, npz_path: Path) -> list[mp.mpf]:
    data = np.load(npz_path, allow_pickle=True)
    return [mp.mpf(x) for x in data["gammas"]]


def get_gammas_cached(cache_dir: Path, *, max_index: int, dps: int, radius: float, N: int) -> list[mp.mpf]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_path, npz_path = gamma_cache_paths(cache_dir, max_index=max_index, dps=dps, radius=radius, N=N)
    if json_path.exists() and npz_path.exists():
        print(f"Loading cached gammas from {npz_path.name}")
        return load_gamma_cache(json_path, npz_path)

    print("Computing gammas via contour / circle sampling...")
    gammas = xi_gammas_contour(max_index=max_index, dps=dps, radius=radius, N=N)
    save_gamma_cache(gammas, json_path, npz_path, max_index=max_index, dps=dps, radius=radius, N=N)
    print(f"Saved gamma cache to {npz_path.name}")
    return gammas


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


def jensen_coeffs(gammas: list[mp.mpf], n: int, d: int) -> list[mp.mpf]:
    if n < 0 or d < 0:
        raise ValueError("n and d must be nonnegative")
    if n + d >= len(gammas):
        raise ValueError(f"Need gamma coefficients through index {n + d}")
    return [mp.binomial(d, j) * gammas[n + j] for j in range(d + 1)]


def roots_polyroots_scaled(coeffs_ascending: list[mp.mpf]) -> list[mp.mpc]:
    """
    Robust polyroots wrapper:
    - convert to descending order
    - normalize to monic
    - choose a variable scale x = s*y from a Cauchy-style bound
    - solve in y
    - map roots back to x
    """
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    # trim leading zeros defensively
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
            {"maxsteps": 1000, "cleanup": False, "extraprec": 120},
        ]
        for opts in attempts:
            try:
                roots_y = mp.polyroots(scaled, **opts)
                return [s * r for r in roots_y]
            except Exception as e:
                last_err = e

    raise last_err


def root_scale(z: complex) -> float:
    return max(1.0, abs(z), abs(z.real), abs(z.imag))


def is_nearly_real(z: complex, rtol: float = 1e-8, atol: float = 1e-12) -> bool:
    return abs(z.imag) <= atol + rtol * root_scale(z)


def count_real_roots(roots: Iterable[complex], rtol: float = 1e-8, atol: float = 1e-12) -> int:
    return sum(is_nearly_real(complex(z), rtol=rtol, atol=atol) for z in roots)


def endpoint_state_proxy(roots: Iterable[complex], rtol: float = 1e-8, atol: float = 1e-12) -> str:
    roots = list(roots)
    return "2" if count_real_roots(roots, rtol=rtol, atol=atol) == len(roots) else "0"


def approx_equal(x: float, y: float, rtol: float = 1e-6, atol: float = 1e-12) -> bool:
    scale = max(1.0, abs(x), abs(y))
    return abs(x - y) <= atol + rtol * scale


def defect_location_proxy(roots: Iterable[complex], rtol: float = 1e-6, atol: float = 1e-12) -> str:
    roots = np.array([complex(z) for z in roots], dtype=np.complex128)
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


def max_rel_imag(roots: Iterable[complex]) -> float:
    vals = [abs(complex(z).imag) / root_scale(complex(z)) for z in roots]
    return float(max(vals)) if vals else 0.0


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


CSV_FIELDS = [
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


def load_completed_n(csv_path: Path) -> set[int]:
    if not csv_path.exists():
        return set()
    done: set[int] = set()
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            done.add(int(row["n"]))
    return done


def ensure_csv_header(csv_path: Path) -> None:
    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_FIELDS)


def append_row(csv_path: Path, row: ScanRow) -> None:
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow(asdict(row))


def scan_one_n(
    gammas: list[mp.mpf],
    n: int,
    *,
    c: float | None = None,
    fixed_d: int | None = None,
    real_rtol: float = 1e-8,
    real_atol: float = 1e-12,
) -> ScanRow | None:
    if (c is None) == (fixed_d is None):
        raise ValueError("Provide exactly one of c or fixed_d")

    d = threshold_degree(n, c) if c is not None else int(fixed_d)
    if d <= 0 or n + d >= len(gammas):
        return None

    coeffs = jensen_coeffs(gammas, n, d)
    roots = roots_polyroots_scaled(coeffs)
    real_count = count_real_roots(roots, rtol=real_rtol, atol=real_atol)

    return ScanRow(
        mode="threshold_ray" if c is not None else "fixed_d",
        c=c,
        fixed_d=fixed_d,
        n=n,
        d=d,
        c_nd=c_nd(n, d),
        real_root_deficit=int(d - real_count),
        endpoint_state=endpoint_state_proxy(roots, rtol=real_rtol, atol=real_atol),
        defect_location=defect_location_proxy(roots, rtol=1e-5, atol=real_atol),
        max_rel_imag=max_rel_imag(roots),
    )


PRESETS = {
    # Keep this as a VALIDATION preset, not a huge scan.
    "c070_poly_validate": {
        "mode": "threshold_ray",
        "c": 0.70,
        "fixed_d": None,
        "n_start": 8,
        "n_stop": 20,
        "dps": 80,
        "max_gamma_index": 90,
        "radius": 0.75,
        "N": 1024,
        "real_rtol": 1e-8,
        "real_atol": 1e-12,
        "output_name": "xi_jensen_poly_scaled_c070_validate.csv",
    },
    "fixed_d_20_poly": {
        "mode": "fixed_d",
        "c": None,
        "fixed_d": 20,
        "n_start": 20,
        "n_stop": 40,
        "dps": 80,
        "max_gamma_index": 80,
        "radius": 0.75,
        "N": 1024,
        "real_rtol": 1e-8,
        "real_atol": 1e-12,
        "output_name": "xi_jensen_poly_scaled_fixed_d20.csv",
    },
}


def parse_args():
    p = argparse.ArgumentParser(description="Scaled contour + polyroots Xi–Jensen scanner")
    p.add_argument("--preset", choices=sorted(PRESETS.keys()))
    p.add_argument("--custom-c", type=float)
    p.add_argument("--fixed-d", type=int)
    p.add_argument("--n-start", type=int)
    p.add_argument("--n-stop", type=int)
    p.add_argument("--dps", type=int)
    p.add_argument("--max-gamma-index", type=int)
    p.add_argument("--radius", type=float)
    p.add_argument("--N", type=int)
    p.add_argument("--real-rtol", type=float)
    p.add_argument("--real-atol", type=float)
    p.add_argument("--output-name", type=str)
    p.add_argument("--cache-dir", type=str, default="gamma_cache")
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
            "n_stop": args.n_stop if args.n_stop is not None else 20,
            "dps": args.dps if args.dps is not None else 80,
            "max_gamma_index": args.max_gamma_index if args.max_gamma_index is not None else 90,
            "radius": args.radius if args.radius is not None else 0.75,
            "N": args.N if args.N is not None else 1024,
            "real_rtol": args.real_rtol if args.real_rtol is not None else 1e-8,
            "real_atol": args.real_atol if args.real_atol is not None else 1e-12,
            "output_name": args.output_name if args.output_name is not None else "xi_jensen_poly_scaled_custom.csv",
        }
    else:
        raise SystemExit("Use --preset, --custom-c, or --fixed-d")

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

    cfg["cache_dir"] = args.cache_dir
    return cfg


def main():
    args = parse_args()
    cfg = config_from_args(args)
    script_dir = Path(__file__).resolve().parent
    out_csv = script_dir / cfg["output_name"]
    cache_dir = script_dir / cfg["cache_dir"]

    print("Threshold constant 1/sqrt(pi) =", threshold_constant())
    print("Config:", cfg)

    gammas = get_gammas_cached(
        cache_dir,
        max_index=cfg["max_gamma_index"],
        dps=cfg["dps"],
        radius=cfg["radius"],
        N=cfg["N"],
    )

    if cfg["c"] is not None and cfg["c"] > threshold_constant():
        c = cfg["c"]
        print(
            f"c={c:.3f}  alpha(c)={alpha_of_c(c):.8g}  "
            f"n0~{n0_scale(c):.6g}  Nc~{Nc_scale(c):.6g}"
        )

    ensure_csv_header(out_csv)
    done = load_completed_n(out_csv)

    total = 0
    written = 0
    for n in range(cfg["n_start"], cfg["n_stop"] + 1):
        total += 1
        if n in done:
            continue
        row = scan_one_n(
            gammas,
            n,
            c=cfg["c"],
            fixed_d=cfg["fixed_d"],
            real_rtol=cfg["real_rtol"],
            real_atol=cfg["real_atol"],
        )
        if row is None:
            continue
        append_row(out_csv, row)
        written += 1
        print(f"Wrote row for n={n}, d={row.d}, deficit={row.real_root_deficit}")

    print(f"Finished. Total n checked: {total}. New rows written: {written}.")
    print(f"CSV: {out_csv}")


if __name__ == "__main__":
    main()
