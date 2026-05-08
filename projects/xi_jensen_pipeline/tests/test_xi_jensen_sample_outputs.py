"""Regression tests for committed Xi-Jensen sample outputs.

These tests guard the headers and key row values of the dashboard smoke
CSVs. If a future refactor changes the column layout or the smoke
numbers without an explicit update here, CI will fail and force us to
either accept the new sample or fix the regression.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_outputs"

FRONTIER_CSV = SAMPLE_DIR / "xi_jensen_dashboard_smoke_frontier.csv"
ROWS_CSV = SAMPLE_DIR / "xi_jensen_dashboard_smoke_rows.csv"

FRONTIER_HEADERS = (
    "c", "c_minus_threshold", "alpha", "n0_pred", "Nc_pred",
    "row_count", "defect_rows",
    "first_defect_n", "first_defect_d", "first_defect_deficit",
    "first_defect_location",
    "sensitive_rows", "verified_rows", "verification_mismatches", "seconds",
)

ROWS_HEADERS = (
    "c", "n", "d", "c_nd",
    "real_root_deficit", "endpoint_state", "defect_location",
    "min_nonreal_abs_imag", "sensitive", "verified", "verified_match",
    "hi_real_root_deficit", "hi_endpoint_state", "hi_defect_location",
)


def _read(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return tuple(reader.fieldnames or ()), rows


# ---------------------------------------------------------------------
# Files exist (early failure if either was renamed/removed)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("path", [FRONTIER_CSV, ROWS_CSV])
def test_sample_csv_exists(path):
    assert path.is_file(), f"missing committed sample: {path}"


# ---------------------------------------------------------------------
# Frontier CSV
# ---------------------------------------------------------------------

def test_frontier_headers_match():
    headers, _ = _read(FRONTIER_CSV)
    assert headers == FRONTIER_HEADERS


def test_frontier_has_one_data_row():
    _, rows = _read(FRONTIER_CSV)
    assert len(rows) == 1


def test_frontier_row_values_remain_locked():
    _, rows = _read(FRONTIER_CSV)
    row = rows[0]
    assert row["c"] == "0.555"
    assert row["row_count"] == "2"
    assert row["defect_rows"] == "2"
    assert row["first_defect_n"] == "3"
    assert row["first_defect_d"] == "2"
    assert row["first_defect_deficit"] == "2"
    assert row["first_defect_location"] == "endpoint_like"
    assert row["sensitive_rows"] == "0"
    assert row["verified_rows"] == "0"
    assert row["verification_mismatches"] == "0"


# ---------------------------------------------------------------------
# Rows CSV
# ---------------------------------------------------------------------

def test_rows_headers_match():
    headers, _ = _read(ROWS_CSV)
    assert headers == ROWS_HEADERS


def test_rows_csv_has_two_data_rows():
    _, rows = _read(ROWS_CSV)
    assert len(rows) == 2


def test_rows_csv_first_row_values():
    _, rows = _read(ROWS_CSV)
    r0 = rows[0]
    assert r0["c"] == "0.555"
    assert r0["n"] == "3"
    assert r0["d"] == "2"
    assert r0["c_nd"] == "0.4034319968705745"
    assert r0["real_root_deficit"] == "2"
    assert r0["defect_location"] == "endpoint_like"


def test_rows_csv_second_row_values():
    _, rows = _read(ROWS_CSV)
    r1 = rows[1]
    assert r1["c"] == "0.555"
    assert r1["n"] == "4"
    assert r1["d"] == "3"
    assert r1["c_nd"] == "0.44152875844330297"
    assert r1["real_root_deficit"] == "2"
    assert r1["defect_location"] == "bulk_like"
