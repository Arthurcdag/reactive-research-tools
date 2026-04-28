Live/resumable threshold frontier explorer
==========================================

Why this version exists
-----------------------
The previous frontier script can look frozen while gamma coefficients are being
computed, and if you interrupt it you lose progress at the frontier level.

This live version adds:
- visible gamma progress (`--verbose-gammas`)
- per-c progress prints
- resumable frontier execution (skip c-values already written)
- incremental writes of:
  - `<prefix>_rows.csv`
  - `<prefix>_frontier.csv`
  - `<prefix>_summary.json`

Best use
--------
If you want a run you can safely stop and restart later:
    python xi_jensen_threshold_frontier_live.py --c-start 0.555 --c-stop 0.575 --c-step 0.005 --n-stop 60 --verify-sensitive --verbose-gammas

If the gamma cache already exists, the c-sweep will begin almost immediately.
If the frontier CSV already exists, completed c-values will be skipped.
