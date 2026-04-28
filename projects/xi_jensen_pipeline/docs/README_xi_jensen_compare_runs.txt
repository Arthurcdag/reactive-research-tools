Xi–Jensen run comparison helper
===============================

What it does
------------
- summarize one or more CSV outputs
- compare two CSV outputs on overlapping (n, d) rows

Why it matters
--------------
We now have several scanner variants:
- targeted
- adrian
- fft
- contour_polyroots_scaled

This script lets you check whether:
- the first defect row matches
- real_root_deficit agrees
- endpoint_state agrees
- defect_location agrees

Examples
--------
Summarize:
    python xi_jensen_compare_runs.py --summary xi_jensen_poly_scaled_c070_validate.csv

Compare two runs:
    python xi_jensen_compare_runs.py --compare xi_jensen_scan_c070.csv xi_jensen_poly_scaled_c070_validate.csv
