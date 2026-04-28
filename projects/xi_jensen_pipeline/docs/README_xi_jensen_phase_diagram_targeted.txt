Updated targeted Xi–Jensen runner
=================================

Files
-----
- xi_jensen_phase_diagram_targeted.py

Why this version
----------------
This is the update script for focused application runs.
It replaces hand-editing of config blocks with:
- presets
- custom c-runs
- output written next to the script

Presets
-------
- c070_fast
- c060_medium
- c057_heavy

Examples
--------
Run the best first supercritical target:
    python xi_jensen_phase_diagram_targeted.py --preset c070_fast

Run the next target:
    python xi_jensen_phase_diagram_targeted.py --preset c060_medium

Custom run:
    python xi_jensen_phase_diagram_targeted.py --custom-c 0.70 --n-start 8 --n-stop 60 --dps 120 --max-gamma-index 80

What to inspect first
---------------------
In the CSV:
- first row with real_root_deficit > 0
- whether defect_location is endpoint_like
- relative onset ordering:
    c = 0.70 earlier than c = 0.60 earlier than c = 0.57

Theory-facing numbers printed
-----------------------------
For supercritical c, the script prints:
- alpha(c)
- n0(c): first-defect scale
- Nc(c): fast-sampling onset scale

Important caution
-----------------
This is still numerically ambitious. The hardest part is generating gamma coefficients.
For serious threshold work:
- scale max_gamma_index gradually
- increase dps only after the pipeline is stable
- verify suspicious cases with root_method = mpmath
