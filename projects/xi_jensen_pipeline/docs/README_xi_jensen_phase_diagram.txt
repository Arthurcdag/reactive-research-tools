Xi–Jensen numerical application runbook
=======================================

Files
-----
- xi_jensen_phase_diagram.py

What this gives you
-------------------
A practical research script to test the threshold-scale theory numerically.

Main observables recorded
-------------------------
- c_nd                finite-n dimensionless degree
- real_root_deficit   d - (# real roots)
- endpoint_state      crude 2 / 0 / amb proxy
- defect_location     heuristic endpoint_like / bulk_like / none

Threshold and supercritical scales
----------------------------------
Threshold constant:
    1/sqrt(pi) ≈ 0.56418958

For c > 1/sqrt(pi):
    kappa = log(c * sqrt(pi))
    alpha(c) = (4c/3) * kappa^(3/2)

Heuristic first-defect scale:
    n0(c) ~ alpha(c)^(-2/3) * (log(1/alpha(c)))^(4/3)

Heuristic fast-sampling onset:
    Nc(c) ~ alpha(c)^(-2) * (log(1/alpha(c)))^4

Recommended first experiment
----------------------------
Use:
    c_values = [0.50, 0.54, 0.56, 0.57, 0.60, 0.70]

Interpretation:
- 0.50, 0.54: clearly subcritical
- 0.56: just below threshold
- 0.57: just above threshold
- 0.60: moderate supercritical
- 0.70: deeper supercritical

Important warning
-----------------
The coefficient extraction via mpmath.taylor gets expensive quickly.
A serious run should:
1. raise dps,
2. raise max_gamma_index in stages,
3. use mpmath root-finding to verify suspicious cases,
4. treat near-threshold classifications as high-precision tasks.

Best validation targets
-----------------------
1. No real-root deficit for c < 1/sqrt(pi)
2. First defects should appear at the endpoint for c > 1/sqrt(pi)
3. Onset around n0(c)
4. Later unstable regime around Nc(c)
5. If extended, cumulative switch counts along fixed c-rays

What I would do next
--------------------
- Run the script on modest n to validate the pipeline
- Increase max_gamma_index and n gradually
- Save separate CSVs per c-ray
- Add a high-precision endpoint-state classifier
