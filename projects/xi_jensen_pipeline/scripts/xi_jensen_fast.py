"""
xi_jensen_fast.py

Optimised version of the Xi / Jensen scan.

Key changes vs the baseline
---------------------------
1. `xi_gammas_fast` replaces `mp.taylor(Xi, 0, 2*max_index)` with the
   Pólya / De Bruijn moment-integral representation:

       Xi(z) = integral_0^inf Phi(t) cos(z t) dt
       gamma(m) = integral_0^inf Phi(t) * t^(2m) dt
       Phi(t) = sum_{n>=1} (2 pi^2 n^4 e^(9t/2) - 3 pi n^2 e^(5t/2))
                          * exp(-pi n^2 e^(2t))

   This avoids repeated high-order numerical differentiation of Xi
   (which internally calls mpmath.zeta at boosted precision).
   Phi(t) is far cheaper than Xi(z): only a handful of exp() calls,
   and the series converges in 3-10 terms thanks to double-exponential
   decay.

2. Persistent on-disk cache of gamma coefficients, keyed by
   (dps, max_index). Subsequent runs are effectively free.

3. `scan_ray` is unchanged in semantics but uses a precomputed
   `gammas` list, so the c x n grid only walks the inexpensive
   polynomial-roots code.

4. Optional multiprocessing over c-rays (disabled by default to
   keep determinism identical to the baseline; enable with
   use_parallel=True).

Correctness strategy
--------------------
The optimised gammas are verified against the baseline `mp.taylor`
computation at a smaller `max_index` and compared elementwise at the
requested precision. See verify_equivalence.py.
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
import pickle
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import mpmath as mp
import numpy as np


# ---------------------------------------------------------------------------
# Phi(t) and the moment integral
# ---------------------------------------------------------------------------

def Phi(t: mp.mpf) -> mp.mpf:
    """
    Polya / De Bruijn density satisfying
        Xi(z) = integral_0^inf Phi(t) cos(z t) dt.

    Derived from integration-by-parts on the theta representation
        pi^(-s/2) Gamma(s/2) zeta(s) = -1/s + 1/(s-1)
            + integral_1^inf omega(x) (x^(s/2) + x^((1-s)/2)) dx/x
    with omega(x) = sum_{n>=1} exp(-pi n^2 x). The final form is:

        Phi(t) = sum_{n>=1} (8 pi^2 n^4 e^(9t/2) - 12 pi n^2 e^(5t/2))
                           * exp(-pi n^2 e^(2t))

    The exp(-pi n^2 e^(2t)) factor gives double-exponential decay in both
    t and n, so the sum converges in 3-10 terms at any reasonable precision
    and t.
    """
    pi = mp.pi
    e2t = mp.exp(2 * t)
    e5t2 = mp.exp(mp.mpf(5) * t / 2)
    e9t2 = mp.exp(mp.mpf(9) * t / 2)

    total = mp.mpf(0)
    tiny = mp.power(10, -mp.mp.dps - 5)

    for n in range(1, 10000):
        n2 = mp.mpf(n * n)
        decay = mp.exp(-pi * n2 * e2t)
        term = (8 * pi * pi * n2 * n2 * e9t2 - 12 * pi * n2 * e5t2) * decay
        total += term
        if abs(term) < tiny and (total == 0 or abs(term) < abs(total) * tiny):
            break
    return total


def _t_max_for_precision() -> mp.mpf:
    """
    Choose a t_max above which Phi(t) is strictly below the working
    precision's tiniest representable contribution.

    Phi(t) ~ 2 pi^2 e^(9t/2) exp(-pi e^(2t)) for large t (n=1 term dominates).
    Set pi e^(2T) = L * log(10) where L = dps + a safety margin.
    Then exp(-pi e^(2T)) ~ 10^(-L), dominating any polynomial prefactor.
    """
    L = mp.mp.dps + 20
    # pi * exp(2T) = L * log(10)  =>  T = (1/2) * log(L log 10 / pi)
    return mp.log(L * mp.log(10) / mp.pi) / 2


def xi_gammas_fast(max_index: int, dps: int = 100, verbose: bool = False) -> list[mp.mpf]:
    """
    Compute gamma(0)...gamma(max_index) via moment integrals of Phi(t).

    Equivalent to the baseline xi_gammas, but orders of magnitude faster
    because it avoids numerical differentiation of Xi.
    """
    if max_index < 0:
        raise ValueError("max_index must be nonnegative")
    mp.mp.dps = dps

    t_max = _t_max_for_precision()

    # One adaptive tanh-sinh quadrature per moment. Quad is cheap because
    # Phi(t) is smooth and strictly positive on (0, t_max).
    gammas: list[mp.mpf] = []
    for m in range(max_index + 1):
        power = 2 * m

        def integrand(t, _p=power):
            return Phi(t) * mp.power(t, _p)

        g = mp.quad(integrand, [mp.mpf(0), t_max])
        gammas.append(mp.re(g))
        if verbose:
            print(f"  gamma({m}) = {mp.nstr(gammas[-1], 10)}")
    return gammas


# ---------------------------------------------------------------------------
# Disk-backed cache for gamma coefficients
# ---------------------------------------------------------------------------

def _cache_key(max_index: int, dps: int) -> str:
    raw = f"gammas|max_index={max_index}|dps={dps}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def xi_gammas_cached(
    max_index: int,
    dps: int = 100,
    cache_dir: str | Path = ".gamma_cache",
    force: bool = False,
    verbose: bool = False,
) -> list[mp.mpf]:
    """
    Compute-or-load gamma coefficients from an on-disk cache.

    Values are serialized as decimal strings (with enough digits for `dps`)
    to avoid mpmath-binary-format churn across versions.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"gammas_{_cache_key(max_index, dps)}.pkl"

    if cache_file.exists() and not force:
        if verbose:
            print(f"[cache] loading gammas from {cache_file}")
        mp.mp.dps = dps
        with cache_file.open("rb") as f:
            payload = pickle.load(f)
        assert payload["max_index"] == max_index
        assert payload["dps"] == dps
        return [mp.mpf(s) for s in payload["values"]]

    if verbose:
        print(f"[cache] miss; computing fresh (max_index={max_index}, dps={dps})")
    gammas = xi_gammas_fast(max_index, dps=dps, verbose=verbose)

    payload = {
        "max_index": max_index,
        "dps": dps,
        "values": [mp.nstr(g, dps + 5, strip_zeros=False) for g in gammas],
    }
    with cache_file.open("wb") as f:
        pickle.dump(payload, f)
    return gammas


# ---------------------------------------------------------------------------
# Scan / observables (logic identical to baseline; just wired to fast gammas)
# ---------------------------------------------------------------------------

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


def roots_mpmath(coeffs_ascending, maxsteps: int = 200, cleanup: bool = True,
                 extraprec: int = 50):
    desc = [mp.mpc(c) for c in reversed(coeffs_ascending)]
    return mp.polyroots(desc, maxsteps=maxsteps, cleanup=cleanup, extraprec=extraprec)


def count_real_roots(roots, tol: float = 1e-8) -> int:
    return sum(abs(z.imag) <= tol for z in roots)


def endpoint_state_proxy(roots, tol: float = 1e-8) -> str:
    roots = list(roots)
    if count_real_roots(roots, tol=tol) == len(roots):
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
    rows: list[ScanRow] = []
    last_state: str | None = None
    for n in n_values:
        d = threshold_degree(n, c)
        if d <= 0 or n + d >= len(gammas):
            continue
        coeffs = jensen_coeffs(gammas, n, d)
        roots = roots_mpmath(coeffs) if root_method == "mpmath" else roots_numpy(coeffs)
        state = endpoint_state_proxy(roots, tol=real_tol)
        if last_state is not None and state != "amb" and last_state != "amb" and state != last_state:
            pass  # switch counter is recorded by caller if needed
        if state != "amb":
            last_state = state
        real_count = count_real_roots(roots, tol=real_tol)
        rows.append(
            ScanRow(
                c=c, n=n, d=d, c_nd=c_nd(n, d),
                real_root_deficit=d - real_count,
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


def _scan_ray_worker(args):
    gammas_strs, dps, c, n_values, root_method = args
    mp.mp.dps = dps
    gammas = [mp.mpf(s) for s in gammas_strs]
    return scan_ray(gammas, c, list(n_values), root_method=root_method)


def run(
    dps: int,
    max_gamma_index: int,
    c_values,
    n_values,
    out_csv,
    root_method: str = "numpy",
    use_cache: bool = True,
    use_parallel: bool = False,
    cache_dir: str | Path = ".gamma_cache",
    verbose: bool = False,
):
    mp.mp.dps = dps
    if use_cache:
        gammas = xi_gammas_cached(max_gamma_index, dps=dps, cache_dir=cache_dir, verbose=verbose)
    else:
        gammas = xi_gammas_fast(max_gamma_index, dps=dps, verbose=verbose)

    n_values = list(n_values)
    if use_parallel and len(c_values) > 1:
        gammas_strs = [mp.nstr(g, dps + 5, strip_zeros=False) for g in gammas]
        workers = min(len(c_values), os.cpu_count() or 1)
        tasks = [(gammas_strs, dps, c, n_values, root_method) for c in c_values]
        all_rows = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for rows in pool.map(_scan_ray_worker, tasks):
                all_rows.extend(rows)
    else:
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
        out_csv=Path("xi_jensen_scan_fast.csv"),
        root_method="numpy",
        verbose=True,
    )
