Xi–Jensen frontier dashboard runner
===================================

What this evolves
-----------------
This is the next version after `xi_jensen_threshold_frontier_live.py`.

It keeps:
- the optimized moment-integral gamma engine
- cached gamma coefficients
- numpy roots as the main production classifier
- optional targeted high-precision verification

It adds:
- theory columns in the frontier CSV:
  - c - 1/sqrt(pi)
  - alpha(c)
  - n0 prediction
  - Nc prediction
- ETA-style timing
- markdown report output
- resumability by completed c-values
- incremental writes after every c

Recommended command
-------------------
python xi_jensen_frontier_dashboard.py --c-start 0.555 --c-stop 0.575 --c-step 0.005 --n-stop 60 --verify-sensitive --verbose-gammas

Outputs
-------
For prefix `xi_jensen_dashboard`, it writes:
- xi_jensen_dashboard_rows.csv
- xi_jensen_dashboard_frontier.csv
- xi_jensen_dashboard_summary.json
- xi_jensen_dashboard_report.md

Fast no-verification run
------------------------
python xi_jensen_frontier_dashboard.py --c-start 0.555 --c-stop 0.575 --c-step 0.005 --n-stop 60
