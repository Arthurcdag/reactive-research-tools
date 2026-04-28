Contour + polyroots Xi–Jensen scanner
=====================================

This version does exactly what was requested:
- contour-integral style coefficient extraction
- polyroots for root finding

Why this version
----------------
The original bottleneck was repeated high-order differentiation of Xi at 0.
This script replaces it with circle sampling / discrete Cauchy extraction.

It also replaces numpy.roots with mpmath.polyroots.

What you get
------------
- cached gamma tables
- resume-safe CSV writing
- relative-tolerance root classification
- theory-ray mode
- fixed-d mode

Recommended first run
---------------------
python xi_jensen_contour_polyroots.py --preset c070_polyroots

Then rerun the same command:
- cached gammas should be reused
- already written n rows should be skipped

Caution
-------
polyroots is numerically nicer for high-precision work, but can be slower than numpy.roots.
So this version is best for:
- smaller targeted scans
- validation passes
- checking suspicious cases found by faster scripts
