Xi-Jensen deepcheck
===================

Purpose
-------
Deepcheck only the hard rows found by triage:
- mismatch rows from `xi_jensen_verify_triage_mismatches.csv`
- optionally failure rows from `xi_jensen_verify_triage_failures.csv`

It uses:
- higher dps,
- larger maxsteps,
- scaled polynomial variable before mp.polyroots,
- root residual diagnostics.

Recommended first command
-------------------------
python xi_jensen_deepcheck.py --limit 13

This deepchecks the 13 mismatch rows only.

Then include failure rows:
--------------------------
python xi_jensen_deepcheck.py --include-failures --limit 21

More aggressive:
----------------
python xi_jensen_deepcheck.py --include-failures --dps 250 --maxsteps 2000 --extraprec 250

Outputs
-------
- xi_jensen_deepcheck_results.csv
- xi_jensen_deepcheck_summary.json
- xi_jensen_deepcheck_report.md

Interpretation
--------------
- `match_lo=True`: the deeper scaled solve agrees with original fast/numpy.
- `match_old_hi=True`: the deeper scaled solve agrees with the previous high-precision verifier.
- low residuals plus stable classification are stronger evidence.
- high residuals or failures mean the row remains numerically unresolved.
