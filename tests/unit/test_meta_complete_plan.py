"""Regression tests for plan-closeout command selection."""

from __future__ import annotations

from pathlib import Path
import sys

from scripts.meta.complete_plan import complete_plan, get_plan_verification_commands


def test_get_plan_verification_commands_reads_command_tables(tmp_path: Path) -> None:
    """Command-based verification tables should be extracted in order."""

    plan_file = tmp_path / "25_example.md"
    plan_file.write_text(
        "# Plan #25: example\n\n"
        "**Status:** In Progress\n\n"
        "## Required Tests\n\n"
        "### New / Explicit Verification For This Plan\n\n"
        "| Command | What It Verifies |\n"
        "|---------|------------------|\n"
        "| `python -c \"print(1)\"` | smoke |\n"
        "| `python -c \"print(2)\"` | smoke |\n"
    )

    assert get_plan_verification_commands(plan_file) == [
        'python -c "print(1)"',
        'python -c "print(2)"',
    ]


def test_complete_plan_uses_declared_command_checks_for_dry_run(tmp_path: Path) -> None:
    """Command-table plans should complete from their declared checks in dry-run mode."""

    project_root = tmp_path
    plans_dir = project_root / "docs" / "plans"
    plans_dir.mkdir(parents=True)

    plan_file = plans_dir / "25_command_mode.md"
    plan_file.write_text(
        "# Plan #25: command mode\n\n"
        "**Status:** In Progress\n"
        "**Type:** implementation\n"
        "**Priority:** High\n"
        "**Blocked By:** None\n"
        "**Blocks:** None\n\n"
        "## Required Tests\n\n"
        "### New / Explicit Verification For This Plan\n\n"
        "| Command | What It Verifies |\n"
        "|---------|------------------|\n"
        f"| `{sys.executable} -c \"print('ok')\"` | smoke |\n"
    )
    (plans_dir / "CLAUDE.md").write_text(
        "# Plans\n\n"
        "| # | Name | Priority | Status | Blocks |\n"
        "|---|------|----------|--------|--------|\n"
        "| 25 | [command mode](25_command_mode.md) | High | 🚧 In Progress | - |\n"
    )

    assert complete_plan(
        plan_number=25,
        project_root=project_root,
        dry_run=True,
        skip_real_e2e=True,
        verbose=False,
    )
