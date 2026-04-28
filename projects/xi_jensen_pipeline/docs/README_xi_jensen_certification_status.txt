Xi-Jensen certification status
==============================

Purpose
-------
Summarize how much of a certified row table is actually deep-certified and suggest high-priority remaining candidates.

Recommended command
-------------------
python xi_jensen_certification_status.py --rows xi_jensen_certified_v2_rows.csv

Outputs
-------
- xi_jensen_certification_status.summary.json
- xi_jensen_certification_status.md
- xi_jensen_certification_status_candidates.csv

Use
---
After every merge, run this to decide the next batch.
