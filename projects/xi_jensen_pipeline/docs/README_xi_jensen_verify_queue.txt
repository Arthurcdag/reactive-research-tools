Xi–Jensen verification queue
============================

Problem solved
--------------
The dashboard is fast until `--verify-sensitive` triggers many high-degree
`mp.polyroots` calls. Those can take a long time or fail to converge.

This script moves verification out of the main scan.

Recommended workflow
--------------------

1. Run the frontier WITHOUT inline verification:

    python xi_jensen_frontier_dashboard.py --c-start 0.555 --c-stop 0.575 --c-step 0.005 --n-stop 60

2. Verify selected rows afterward:

    python xi_jensen_verify_queue.py --rows xi_jensen_dashboard_rows.csv --max-d 60 --limit 50

Useful variants
---------------
Only rows marked sensitive:

    python xi_jensen_verify_queue.py --rows xi_jensen_dashboard_rows.csv --only-sensitive --max-d 60

Avoid hard high-degree cases:

    python xi_jensen_verify_queue.py --rows xi_jensen_dashboard_rows.csv --max-d 50

Verify a narrow n-window:

    python xi_jensen_verify_queue.py --rows xi_jensen_dashboard_rows.csv --min-n 30 --max-n 45 --max-d 80

Why max-d exists
----------------
Your log shows failures mostly around degree 67 and higher. A degree gate lets
you verify the reliable smaller cases first, and treat high-degree verification
as a separate harder task.
