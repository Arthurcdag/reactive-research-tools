Extended experiments for xi_jensen_fast
=======================================

Why this version exists
-----------------------
The optimized engine already solved the main bottleneck:
- baseline used `mp.taylor(Xi, 0, 2*max_index)`
- fast version uses the Pólya / De Bruijn moment-integral plus a cache
- the uploaded report says this reduced the client-sized run from about
  9 hours to about 18 seconds cold, with a warm cache hit around 40 ms,
  while preserving byte-identical CSV output and stable labels under a
  higher-precision verification pass.

This runner evolves that fast path for actual research experiments:
- larger-n presets
- automatic max_gamma_index sizing
- per-c summaries
- targeted verification only for sensitive rows

Design choice
-------------
This script keeps numpy roots as the default main scan path.
`mp.polyroots` is used only for targeted verification of rows whose smallest
nonzero imaginary part is close to the classification tolerance.

Suggested runs
--------------
Client reproducibility:
    python xi_jensen_fast_experiments.py --preset client_full

Extended c=0.70 experiment:
    python xi_jensen_fast_experiments.py --preset c070_extended

Extended c=0.60 experiment:
    python xi_jensen_fast_experiments.py --preset c060_extended

Threshold band:
    python xi_jensen_fast_experiments.py --preset threshold_band_extended

Write a JSON summary:
    python xi_jensen_fast_experiments.py --preset c070_extended --summary-json c070_summary.json
