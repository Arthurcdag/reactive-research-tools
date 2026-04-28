Lite Xi–Jensen application notes
================================

Files
-----
- xi_jensen_phase_diagram_lite.py
- xi_jensen_lite_sample.csv

Purpose
-------
This is a fast emulation version of the heavier Xi–Jensen scan. It is only for:
- validating the pipeline,
- confirming that coefficient extraction, polynomial building, and root finding work,
- giving a quick sample output inside this session.

Important warning
-----------------
The included sample run uses:
- very small n,
- low precision,
- a tiny coefficient table,
- numpy roots.

So it should NOT be interpreted as evidence for or against the asymptotic threshold
law near 1/sqrt(pi). Small-n behavior is not the target regime of the theory.

Why this version helps
----------------------
It lets you:
- confirm the code path works,
- iterate on observables and CSV layout,
- profile runtime cheaply,
- decide how to scale the heavier script.

Suggested next use
------------------
1. Run the lite version first.
2. If it behaves as expected, raise max_gamma_index slowly.
3. Then raise dps.
4. Then move selected near-threshold cases to high-precision root checks.
