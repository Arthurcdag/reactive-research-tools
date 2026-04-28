Threshold frontier explorer for xi_jensen_fast
==============================================

Why this exists
---------------
The fast engine now reproduces the client CSV exactly and runs quickly enough
that the next natural step is a real frontier experiment: sweep c and ask
where the first defect appears.

What it writes
--------------
- `<prefix>_rows.csv`      full row-level output
- `<prefix>_frontier.csv`  one line per c with first-defect information
- `<prefix>_summary.json`  machine-readable run summary

Suggested runs
--------------
Broad threshold band:
    python xi_jensen_threshold_frontier.py --c-start 0.54 --c-stop 0.60 --c-step 0.01 --n-stop 40

Near-threshold finer sweep:
    python xi_jensen_threshold_frontier.py --c-start 0.555 --c-stop 0.575 --c-step 0.005 --n-stop 60

With targeted verification:
    python xi_jensen_threshold_frontier.py --verify-sensitive
