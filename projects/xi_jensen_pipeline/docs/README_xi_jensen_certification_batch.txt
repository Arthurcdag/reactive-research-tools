Xi-Jensen certification batch
=============================

Why this exists
---------------
The old verifier queue uses ordinary polyroots and compares against original
fast labels. After `xi_jensen_certified_rows.csv` exists, later certification
passes should use the scaled deepcheck solver directly and compare against the
current certified labels.

Recommended next command
------------------------
Start with a moderate batch:

    python xi_jensen_certification_batch.py --rows xi_jensen_certified_rows.csv --min-n 20 --max-d 60 --limit 25

Append another batch:

    python xi_jensen_certification_batch.py --rows xi_jensen_certified_rows.csv --min-n 20 --max-d 80 --limit 25 --append

Focus on untouched c-values:

    python xi_jensen_certification_batch.py --rows xi_jensen_certified_rows.csv --c-values 0.565,0.57,0.575 --min-n 15 --max-d 60 --limit 40

After each batch
----------------
Merge the batch results:

    python xi_jensen_certified_merge.py --rows xi_jensen_certified_rows.csv --deepcheck xi_jensen_certification_batch_results.csv --prefix xi_jensen_certified_v2

Then continue from:

    xi_jensen_certified_v2_rows.csv

New loop
--------
certified rows -> certification batch -> certified merge -> repeat
