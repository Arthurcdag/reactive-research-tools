Xi-Jensen certified merge v2
============================

Why v2 exists
-------------
The first certified merge was fine for one merge, but repeated certification passes need to preserve already-certified labels when the new deepcheck CSV only contains the latest batch.

This v2 merge is iteration-safe:
- existing certified_* labels are preserved if no new deepcheck row is supplied
- new successful scaled deepcheck rows replace the current certified label
- failed deepchecks do not destroy an existing certification
- multiple deepcheck CSVs can be supplied at once
- duplicate deepcheck keys prefer successful rows with lower residuals

Recommended use after a certification batch
-------------------------------------------
python xi_jensen_certified_merge_v2.py --rows xi_jensen_certified_rows.csv --deepcheck xi_jensen_certification_batch_results.csv --prefix xi_jensen_certified_v2

Multiple deepcheck files
------------------------
python xi_jensen_certified_merge_v2.py --rows xi_jensen_certified_v2_rows.csv --deepcheck old_results.csv new_results.csv --prefix xi_jensen_certified_v3

Optional residual gate
----------------------
python xi_jensen_certified_merge_v2.py --rows xi_jensen_certified_rows.csv --deepcheck xi_jensen_certification_batch_results.csv --residual-gate 1e-40
