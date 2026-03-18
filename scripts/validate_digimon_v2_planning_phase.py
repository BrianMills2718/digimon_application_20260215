#!/usr/bin/env python3
"""Validate DIGIMON v2 planning-phase artifacts and emit execution evidence.

This script exists to make the rebuild planning package fail-loud and machine
checkable. It verifies that the expected plan, architecture blueprint, and
acceptance gate exist, contain required sections, and stay consistent with the
config-driven contract for Phase 0. Successful validation writes a JSON report
that becomes the evidence artifact for the planning phase.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


LOGGER = logging.getLogger("digimon_v2_planning_phase")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class PlanningPhaseSettings(BaseModel):
    """Configuration for the DIGIMON v2 planning-phase validator."""

    gate_path: str = Field(min_length=1)
    plan_path: str = Field(min_length=1)
    architecture_path: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    required_plan_headings: list[str] = Field(min_length=1)
    required_architecture_headings: list[str] = Field(min_length=1)
    required_architecture_phases: list[str] = Field(min_length=1)


class ValidatorConfig(BaseModel):
    """Top-level config model for this validator."""

    digimon_v2_planning_phase: PlanningPhaseSettings


class AcceptanceCriterion(BaseModel):
    """One machine-readable acceptance criterion."""

    id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    category: str = Field(min_length=1)
    given: list[str] = Field(default_factory=list)
    when: str = Field(min_length=1)
    then: list[str] = Field(default_factory=list)
    locked: bool = False


class AcceptanceGate(BaseModel):
    """Acceptance-gate model for the planning package."""

    feature: str = Field(min_length=1)
    planning_mode: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    design: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    out_of_scope: list[str] = Field(default_factory=list)
    adrs: list[int] = Field(default_factory=list)
    code: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class CheckResult:
    """One executed validation check."""

    name: str
    passed: bool
    details: str


def configure_logging(verbose: bool) -> None:
    """Configure logging for the validator."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s")


def load_yaml_file(path: Path) -> Any:
    """Load a YAML file and fail loudly on parse errors."""

    LOGGER.info("loading_yaml path=%s", path)
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_validator_config(path: Path) -> ValidatorConfig:
    """Load and validate the validator config file."""

    raw = load_yaml_file(path)
    try:
        return ValidatorConfig.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid validator config at {path}: {exc}") from exc


def load_acceptance_gate(path: Path) -> AcceptanceGate:
    """Load and validate the acceptance gate."""

    raw = load_yaml_file(path)
    try:
        return AcceptanceGate.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid acceptance gate at {path}: {exc}") from exc


def ensure_file_exists(path: Path, label: str) -> CheckResult:
    """Check that a required file exists."""

    exists = path.exists()
    details = f"{label} path={display_path(path)}"
    LOGGER.info("check_exists label=%s passed=%s path=%s", label, exists, path)
    return CheckResult(name=f"{label}_exists", passed=exists, details=details)


def ensure_headings_present(content: str, headings: list[str], label: str) -> CheckResult:
    """Check that all required headings appear in a document."""

    missing = [heading for heading in headings if heading not in content]
    passed = not missing
    details = f"{label} missing_headings={missing}" if missing else f"{label} all headings present"
    LOGGER.info("check_headings label=%s passed=%s missing=%s", label, passed, missing)
    return CheckResult(name=f"{label}_headings", passed=passed, details=details)


def ensure_architecture_phases_present(content: str, phases: list[str]) -> CheckResult:
    """Check that every required phase heading appears in the architecture doc."""

    missing = [phase for phase in phases if phase not in content]
    passed = not missing
    details = (
        f"architecture missing phases={missing}"
        if missing
        else f"architecture phases present count={len(phases)}"
    )
    LOGGER.info("check_architecture_phases passed=%s missing=%s", passed, missing)
    return CheckResult(name="architecture_phases", passed=passed, details=details)


def ensure_gate_references_exist(gate: AcceptanceGate, project_root: Path) -> CheckResult:
    """Check that files named in the acceptance gate exist in the repo."""

    referenced_paths = gate.code + gate.tests + gate.docs
    missing = [path for path in referenced_paths if not (project_root / path).exists()]
    passed = not missing
    details = (
        f"gate missing referenced_paths={missing}"
        if missing
        else f"gate references resolved count={len(referenced_paths)}"
    )
    LOGGER.info("check_gate_references passed=%s missing=%s", passed, missing)
    return CheckResult(name="gate_references", passed=passed, details=details)


def ensure_gate_shape(gate: AcceptanceGate) -> CheckResult:
    """Check that the gate has the minimum planning-phase structure."""

    passed = (
        gate.feature == "digimon_v2_planning_phase"
        and len(gate.acceptance_criteria) >= 3
        and bool(gate.docs)
        and bool(gate.tests)
    )
    details = (
        "gate structure valid"
        if passed
        else "gate must define feature digimon_v2_planning_phase, >=3 acceptance criteria, docs, and tests"
    )
    LOGGER.info("check_gate_shape passed=%s", passed)
    return CheckResult(name="gate_shape", passed=passed, details=details)


def build_report(
    checks: list[CheckResult],
    config_path: Path,
    gate_path: Path,
    plan_path: Path,
    architecture_path: Path,
) -> dict[str, Any]:
    """Build the JSON evidence report payload."""

    passed = all(check.passed for check in checks)
    return {
        "phase": "digimon_v2_planning_phase",
        "passed": passed,
        "config_path": display_path(config_path),
        "gate_path": display_path(gate_path),
        "plan_path": display_path(plan_path),
        "architecture_path": display_path(architecture_path),
        "checks": [
            {"name": check.name, "passed": check.passed, "details": check.details}
            for check in checks
        ],
    }


def display_path(path: Path) -> str:
    """Render a path relative to the repo root when possible."""

    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def validate_planning_phase(config_path: Path, report_path_override: Path | None = None) -> dict[str, Any]:
    """Validate the planning-phase package and write the evidence report."""

    config = load_validator_config(config_path)
    settings = config.digimon_v2_planning_phase

    gate_path = PROJECT_ROOT / settings.gate_path
    plan_path = PROJECT_ROOT / settings.plan_path
    architecture_path = PROJECT_ROOT / settings.architecture_path
    report_path = report_path_override or (PROJECT_ROOT / settings.report_path)

    checks = [
        ensure_file_exists(config_path, "config"),
        ensure_file_exists(gate_path, "gate"),
        ensure_file_exists(plan_path, "plan"),
        ensure_file_exists(architecture_path, "architecture"),
    ]
    if not all(check.passed for check in checks):
        report = build_report(checks, config_path, gate_path, plan_path, architecture_path)
        write_report(report_path, report)
        raise RuntimeError("DIGIMON v2 planning-phase validation failed before content checks")

    gate = load_acceptance_gate(gate_path)
    plan_content = plan_path.read_text(encoding="utf-8")
    architecture_content = architecture_path.read_text(encoding="utf-8")

    checks.extend(
        [
            ensure_headings_present(plan_content, settings.required_plan_headings, "plan"),
            ensure_headings_present(
                architecture_content,
                settings.required_architecture_headings,
                "architecture",
            ),
            ensure_architecture_phases_present(
                architecture_content,
                settings.required_architecture_phases,
            ),
            ensure_gate_shape(gate),
            ensure_gate_references_exist(gate, PROJECT_ROOT),
        ]
    )

    report = build_report(checks, config_path, gate_path, plan_path, architecture_path)
    write_report(report_path, report)

    if not report["passed"]:
        raise RuntimeError("DIGIMON v2 planning-phase validation failed; inspect the evidence report")

    return report


def write_report(report_path: Path, report: dict[str, Any]) -> None:
    """Write the JSON evidence report."""

    LOGGER.info("writing_report path=%s", report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the validator."""

    parser = argparse.ArgumentParser(description="Validate DIGIMON v2 planning-phase artifacts")
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the validator config file",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Optional override for the output evidence report path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> int:
    """Run the validator and emit a non-zero exit code on failure."""

    args = parse_args()
    configure_logging(args.verbose)
    try:
        report = validate_planning_phase(args.config_path, args.report_path)
    except Exception as exc:  # noqa: BLE001 - fail-loud CLI boundary
        LOGGER.error("validation_failed error=%s", exc)
        return 1

    LOGGER.info("validation_passed phase=%s", report["phase"])
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
