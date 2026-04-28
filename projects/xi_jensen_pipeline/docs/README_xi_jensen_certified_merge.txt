Xi-Jensen certified merge
=========================

Purpose
-------
Merge the fast dashboard scan with the deepcheck results.

This creates a certified row table:
- uses the fast/numpy label for ordinary unverified rows
- replaces labels with deep scaled-polyroots labels where deepcheck succeeded
- keeps provenance columns so you know which labels came from which layer

Recommended command
-------------------
python xi_jensen_certified_merge.py --rows xi_jensen_dashboard_rows.csv --deepcheck xi_jensen_deepcheck_results.csv

Outputs
-------
With default prefix:
- xi_jensen_certified_rows.csv
- xi_jensen_certified_frontier.csv
- xi_jensen_certified_summary.json
- xi_jensen_certified_report.md

Optional residual gate
----------------------
Accept deepcheck labels only if the max relative residual is below a threshold:

python xi_jensen_certified_merge.py --residual-gate 1e-40

Interpretation
--------------
- certified_source=fast_numpy: label came from the fast production scan.
- certified_source=deep_scaled_polyroots: label was replaced by deepcheck.
- certified_status=deepcheck_ok: deepcheck succeeded and was accepted.
- certified_status=unverified: row was not in the deepcheck set.
