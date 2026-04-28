Scaled contour + polyroots Xi–Jensen scanner
============================================

Why this version exists
-----------------------
The first contour+polyroots attempt failed because polyroots was fed badly
scaled Jensen polynomials.

This patched version fixes that by:
- making the polynomial monic
- scaling the variable using a Cauchy-bound heuristic
- retrying polyroots with safer settings

Best use
--------
This is a validation runner, not the main broad scanner.

Recommended first run
---------------------
python xi_jensen_contour_polyroots_scaled.py --preset c070_poly_validate

What to expect
--------------
- contour extraction should load from cache after the first run
- n=8..20 should be a manageable validation window
- this is the right tool for checking suspicious cases found by faster scanners

Main lesson
-----------
- contour extraction is the good idea
- polyroots needs scaling to behave well
- use this for targeted validation, not huge sweeps
