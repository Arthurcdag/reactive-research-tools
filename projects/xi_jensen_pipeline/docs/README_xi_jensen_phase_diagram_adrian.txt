Adrian version: faster + relative-tolerance Xi–Jensen scanner
=============================================================

What changed
------------
1. Faster coefficient extraction:
   - old approach: repeated high-order differentiation of Xi at 0
   - new approach: circle sampling + discrete Cauchy/DFT extraction

2. Relative root classification:
   - old approach: absolute imaginary threshold only
   - new approach:
         |Im z| <= atol + rtol * max(1, |z|, |Re z|, |Im z|)
   so the decision scales with root size.

3. Optional fixed-d mode:
   - keeps the theory ray
         d = floor(c n^(3/2)/sqrt(log n))
     when you want it
   - also lets you run an explicit fixed degree if you just want faster experiments

Good first runs
---------------
Theory-ray run:
    python xi_jensen_phase_diagram_adrian.py --preset c070_fast

Fixed-degree demo:
    python xi_jensen_phase_diagram_adrian.py --preset fixed_d_20_demo

Custom threshold-ray run:
    python xi_jensen_phase_diagram_adrian.py --custom-c 0.70 --n-start 8 --n-stop 60

Custom fixed-degree run:
    python xi_jensen_phase_diagram_adrian.py --fixed-d 20 --n-start 20 --n-stop 80

What to inspect
---------------
- first row with real_root_deficit > 0
- defect_location
- max_rel_imag
- onset ordering between c=0.70 and c=0.60

Caution
-------
This is still a research prototype.
Before trusting larger runs, compare a few small cases against the older script.
