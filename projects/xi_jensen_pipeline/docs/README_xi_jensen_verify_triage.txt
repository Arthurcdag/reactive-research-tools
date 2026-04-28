Xi-Jensen verification triage
=============================

Why this exists
---------------
The verification queue produced three kinds of information:
- successful high-precision checks,
- failed mp.polyroots rows,
- and mismatches between the fast/numpy label and high-precision/polyroots label.

This script reads `xi_jensen_verify_queue_results.csv` and produces:
- a JSON summary
- a markdown triage report
- a mismatches-only CSV
- a failures-only CSV

Recommended command
-------------------
python xi_jensen_verify_triage.py --verify-results xi_jensen_verify_queue_results.csv --rows xi_jensen_dashboard_rows.csv

Outputs
-------
With default prefix:
- xi_jensen_verify_triage.summary.json
- xi_jensen_verify_triage.md
- xi_jensen_verify_triage_mismatches.csv
- xi_jensen_verify_triage_failures.csv

Interpretation
--------------
Mismatches are not automatically theory failure. They mark rows where
numpy-float64 classification and high-precision polyroots classification
disagree. Those become the next inspection set.

Failures are not automatically false. They mean mp.polyroots did not converge
under the chosen settings. Those rows should be moved to a separate
high-degree/certification workflow.
