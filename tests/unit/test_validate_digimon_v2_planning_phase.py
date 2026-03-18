"""Tests for the DIGIMON v2 planning-phase validator.

These tests execute the real validator against real repo artifacts so the
planning package has executable acceptance evidence. They also verify that the
validator fails loudly when a required file path is broken.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "validate_digimon_v2_planning_phase.py"
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def test_validator_passes_for_repo_artifacts(tmp_path: Path) -> None:
    """The planning package should validate successfully and write a report."""

    report_path = tmp_path / "planning_phase_report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--config-path",
            str(CONFIG_PATH),
            "--report-path",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["phase"] == "digimon_v2_planning_phase"
    assert report["passed"] is True
    assert report["config_path"] == "config/config.yaml"
    assert report["gate_path"] == "acceptance_gates/digimon_v2_planning_phase.yaml"
    assert report["plan_path"] == "docs/plans/02_digimon_v2_greenfield_planning_phase.md"
    assert report["architecture_path"] == "docs/planning/digimon_v2/ARCHITECTURE.md"
    assert all(str(PROJECT_ROOT) not in check["details"] for check in report["checks"])
    assert all(check["passed"] for check in report["checks"])


def test_validator_fails_for_missing_required_file(tmp_path: Path) -> None:
    """The validator should fail loudly when config points at a missing artifact."""

    broken_config_path = tmp_path / "broken_config.yaml"
    report_path = tmp_path / "broken_report.json"
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    config["digimon_v2_planning_phase"]["plan_path"] = "docs/plans/DOES_NOT_EXIST.md"
    broken_config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--config-path",
            str(broken_config_path),
            "--report-path",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert any(check["name"] == "plan_exists" and not check["passed"] for check in report["checks"])
