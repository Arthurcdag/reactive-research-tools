"""CLI smoke tests for the Xi-Jensen pipeline.

We invoke the script's argparse ``--help`` path only. That exercises:

* the script can be discovered and executed by Python,
* its top-level imports resolve (mpmath, numpy, sibling scripts),
* its ``argparse.ArgumentParser`` is constructed without runtime errors.

We deliberately do NOT run any numerical work: certification campaigns,
deepcheck batches, frontier sweeps, contour stress harnesses, or
high-precision verification. Those are out of scope for CI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

# CLI scripts that the spec asks CI to smoke. Both exist in scripts/.
_HELP_TARGETS = (
    "xi_jensen_frontier_dashboard.py",
    "xi_jensen_certification_status.py",
)


def _run_help(script_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SCRIPTS_DIR),
    )


@pytest.mark.parametrize("script_name", _HELP_TARGETS)
def test_cli_help_exits_zero(script_name):
    result = _run_help(script_name)
    assert result.returncode == 0, (
        f"{script_name} --help exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.parametrize("script_name", _HELP_TARGETS)
def test_cli_help_prints_usage_line(script_name):
    result = _run_help(script_name)
    assert result.stdout.lower().startswith("usage:"), (
        f"{script_name} --help did not start with 'usage:': {result.stdout[:80]!r}"
    )
    assert script_name in result.stdout, (
        f"{script_name} --help output did not name the script: {result.stdout[:200]!r}"
    )
