# Xi–Jensen Certification Pipeline

This directory contains the scripts developed for the Xi–Jensen numerical/certification workflow.

## Workflow

```text
fast dashboard scan
-> certification batch
-> certified merge v2
-> certification status
-> repeat
```

Earlier exploratory layers are also included:
- contour/polyroots experiments,
- sanity benchmarks,
- threshold-frontier runners,
- verification queues,
- triage scripts,
- deepcheck scripts.

## Main scripts

Recommended current loop:

```bash
python scripts/xi_jensen_frontier_dashboard.py --c-start 0.555 --c-stop 0.575 --c-step 0.005 --n-stop 60

python scripts/xi_jensen_certification_batch.py --rows xi_jensen_certified_rows.csv --min-n 20 --max-d 80 --limit 25

python scripts/xi_jensen_certified_merge_v2.py --rows xi_jensen_certified_rows.csv --deepcheck xi_jensen_certification_batch_results.csv --prefix xi_jensen_certified_v2

python scripts/xi_jensen_certification_status.py --rows xi_jensen_certified_v2_rows.csv
```

## Interpretation

- `fast_numpy` is the exploratory/candidate label source.
- `deep_scaled_polyroots` is the certification label source.
- `unverified` rows should not be treated as final.
- `deepcheck_ok` rows are stronger, but residual diagnostics should still be inspected for publication-level claims.
