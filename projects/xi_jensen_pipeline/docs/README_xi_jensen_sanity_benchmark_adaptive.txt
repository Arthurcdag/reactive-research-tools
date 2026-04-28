Adaptive Xi–Jensen sanity benchmark
===================================

What changed
------------
This version automatically computes enough gamma coefficients for the chosen
n-window and degree rule, so the root comparison actually runs.

Recommended run
---------------
python xi_jensen_sanity_benchmark_adaptive.py

This is the right next check if you want to validate:
- contour gamma extraction against the derivative method
- numpy vs scaled polyroots on a tiny real overlap window
