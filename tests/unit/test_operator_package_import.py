"""Unit tests for import hygiene in the operator package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_core_operators_package_import_keeps_optional_operator_modules_lazy() -> None:
    """Importing the package should not eagerly import optional operator deps.

    The direct benchmark backend only needs ``OperatorContext``. Importing that
    path must not drag in unrelated operator modules such as TF-IDF, which in
    turn depend on optional packages not required for context construction.
    """

    repo_root = Path(__file__).resolve().parents[2]
    script = """
import importlib
import sys

operators = importlib.import_module("Core.Operators")
assert operators.OperatorContext.__name__ == "OperatorContext"
assert "Core.Operators.entity.tfidf" not in sys.modules
assert "Core.Index.TFIDFStore" not in sys.modules
print("lazy-import-ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip() == "lazy-import-ok"
