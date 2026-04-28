Fast research runner for xi_jensen_fast
=======================================

What this does
--------------
This script keeps the optimized `xi_jensen_fast` engine as the main path and
adds:
- named presets
- focused scans
- automatic first-defect summary
- optional comparison against an expected CSV
- optional JSON summary output

Why this is the right evolution
-------------------------------
The optimization report already shows:
- the old bottleneck was `mp.taylor(Xi, 0, 2*max_index)`
- the moment-integral replacement plus cache cuts runtime from about 9 hours
  to about 18 seconds on the client's default config
- warm reruns are about 40 ms
- classifications stayed stable under higher-precision validation

So this wrapper evolves the *fast* path, not the slower polyroots-first path.

Examples
--------
Run the client's full config:
    python xi_jensen_fast_research.py --preset client_full

Focused c=0.70 run:
    python xi_jensen_fast_research.py --preset c070_fast

Threshold-band run:
    python xi_jensen_fast_research.py --preset threshold_band

Compare against an expected CSV:
    python xi_jensen_fast_research.py --preset client_full --compare-to expected_client.csv

Write a machine-readable summary:
    python xi_jensen_fast_research.py --preset client_full --summary-json run_summary.json
