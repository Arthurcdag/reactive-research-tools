"""Pure-function unit tests for the Xi-Jensen pipeline.

Scope: only stable arithmetic helpers that do not require numerical
campaigns, deep certification, high-precision sweeps, or network calls.
These run in well under a second on CI.
"""
from __future__ import annotations

import math

import pytest

import xi_jensen_baseline as B
import xi_jensen_fast as F
import xi_jensen_fast_experiments as E


# ---------------------------------------------------------------------
# threshold_degree
# ---------------------------------------------------------------------

def test_threshold_degree_baseline_smoke_value():
    assert B.threshold_degree(3, 0.555) == 2


def test_threshold_degree_fast_matches_baseline_for_smoke_value():
    assert F.threshold_degree(3, 0.555) == B.threshold_degree(3, 0.555)


def test_threshold_degree_n_equals_4_smoke_value():
    # n=4, c=0.555: floor(0.555 * 4**1.5 / sqrt(log(4))) = 3
    assert B.threshold_degree(4, 0.555) == 3


@pytest.mark.parametrize("bad_n", [2, 1, 0, -1, -100])
def test_threshold_degree_rejects_n_below_three(bad_n):
    with pytest.raises(ValueError, match="n must be at least 3"):
        B.threshold_degree(bad_n, 0.555)


@pytest.mark.parametrize("bad_n", [2, 1, 0, -1])
def test_threshold_degree_fast_rejects_n_below_three(bad_n):
    with pytest.raises(ValueError, match="n must be at least 3"):
        F.threshold_degree(bad_n, 0.555)


# ---------------------------------------------------------------------
# c_nd
# ---------------------------------------------------------------------

def test_c_nd_matches_smoke_csv_value_for_n3_d2():
    # Locked-in value from sample_outputs/xi_jensen_dashboard_smoke_rows.csv
    expected = 0.4034319968705745
    assert math.isclose(B.c_nd(3, 2), expected, rel_tol=1e-12)


def test_c_nd_matches_smoke_csv_value_for_n4_d3():
    # Locked-in value from sample_outputs/xi_jensen_dashboard_smoke_rows.csv
    expected = 0.44152875844330297
    assert math.isclose(B.c_nd(4, 3), expected, rel_tol=1e-12)


def test_c_nd_fast_matches_baseline():
    assert F.c_nd(3, 2) == B.c_nd(3, 2)
    assert F.c_nd(4, 3) == B.c_nd(4, 3)


# ---------------------------------------------------------------------
# auto_max_gamma_index
# ---------------------------------------------------------------------

def test_auto_max_gamma_index_smoke_value():
    # For c=0.555 across n in {3, 4}: max(n + threshold_degree(n, c)) = 7,
    # plus default-ish safety=4 → 11.
    assert E.auto_max_gamma_index([0.555], [3, 4], safety=4) == 11


def test_auto_max_gamma_index_safety_zero_drops_padding():
    # Same scan without safety leaves the bare max(n + d).
    assert E.auto_max_gamma_index([0.555], [3, 4], safety=0) == 7


def test_auto_max_gamma_index_accepts_iterables_not_lists():
    # The signature takes Iterable; a generator must work too.
    def c_gen():
        yield 0.555

    def n_gen():
        yield 3
        yield 4

    assert E.auto_max_gamma_index(c_gen(), n_gen(), safety=4) == 11
