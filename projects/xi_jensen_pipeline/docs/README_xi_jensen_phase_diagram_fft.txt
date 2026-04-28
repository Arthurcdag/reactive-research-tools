FFT/Cauchy Xi–Jensen scanner
============================

Why this exists
---------------
The original bottleneck was extracting many gamma(n) coefficients of Xi by
high-order differentiation at 0. This prototype replaces that with circular
sampling + discrete Cauchy coefficient extraction.

Core idea
---------
If
    Xi(z) = sum_{m>=0} a_m z^m,
then for a circle |z| = R one can approximate
    a_m = (1/N) sum_k Xi(R e^{2πik/N}) e^{-2π i m k / N} / R^m

Then
    gamma(m) = (-1)^m (2m)! a_{2m}.

Why it may help
---------------
- batch coefficient extraction
- no repeated high-order differentiation
- often much faster for moderate coefficient ranges

Caution
-------
This is a research prototype.
You should compare a few low-order gamma(m) values against the derivative-based
script before trusting larger runs.

Suggested first run
-------------------
python xi_jensen_phase_diagram_fft.py --preset c070_fast

Then compare:
- runtime
- first defect row
- defect localization
against the original targeted runner.
