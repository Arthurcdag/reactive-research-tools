Xi–Jensen sanity benchmark
==========================

What this script answers
------------------------
1. Do derivative-based and contour-based gamma tables agree at low order?
2. Is contour extraction actually faster on a small benchmark?
3. On a small overlap window, do numpy roots and scaled polyroots agree?

Recommended run
---------------
python xi_jensen_sanity_benchmark.py

Suggested use
-------------
Run this before trusting larger contour-based scans.
If gamma agreement looks good at low order and contour is faster, that supports
using the contour extractor as the main path.
