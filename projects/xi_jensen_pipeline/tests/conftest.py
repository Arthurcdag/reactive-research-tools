"""Local conftest for the xi_jensen_pipeline test tree.

Xi-Jensen scripts currently import each other as top-level script modules
(e.g. ``import xi_jensen_fast as F``). To let pytest collect tests that
import those modules without packaging the scripts, we prepend the
scripts directory to ``sys.path``.

The injection is scoped to this directory's conftest so it does not
affect the effective_boolean_filter test tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
