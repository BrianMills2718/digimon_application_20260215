"""Unit tests for the extraction-iteration supervisor thin slice."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.run_extraction_iteration_supervisor import (
    AgentConfig,
    ExtractionIterationConfig,
    FamilyConfig,
    RuntimeConfig,
    extract_variant_mean_score,
    has_strictly_improved,
    load_config,
    read_state,
    run_loop,
)


def _run_git(repo_root: Path, *args: str) -> str:
    """Run a git command inside a temporary repository and return stdout."""

    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_prompt_eval_artifact(path: Path, *, variant_name: str, mean_score: float) -> None:
    """Write the smallest prompt-eval JSON payload the supervisor needs to read."""

    payload = {
        "experiment": {
            "summary": {
                variant_name: {
                    "mean_score": mean_score,
                }
            }
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _init_temp_repo(repo_root: Path) -> None:
    """Create a small real git repo for supervisor loop tests."""

    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".gitignore").write_text("results/\n", encoding="utf-8")
    (repo_root / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(repo_root), check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "digimon-tests@example.com"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "DIGIMON Tests"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "add", ".gitignore", "tracked.txt"], cwd=str(repo_root), check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial state"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )


def _build_config(repo_root: Path) -> ExtractionIterationConfig:
    """Return a narrow supervisor config for unit-test loop execution."""

    return ExtractionIterationConfig(
        repo_root=repo_root,
        runtime=RuntimeConfig(
            python_command=["./.venv/bin/python", "-u"],
            duration_hours=0.001,
            validation_timeout_seconds=60,
            agent_timeout_seconds=60,
            sleep_on_noop_seconds=0,
            results_root=Path("results/continuous_extraction"),
        ),
        family=FamilyConfig(
            name="grounded_named_endpoint_completeness",
            cases_file=Path("eval/fixtures/musique_tkg_extraction_prompt_eval_cases.json"),
            prompt_family="two_pass_entity_inventory",
            target_variant="grounded_entity_contract",
            production_model="gemini/gemini-2.5-flash",
            n_runs=1,
            comparison_method="paired_t",
        ),
        agent=AgentConfig(
            selection_task="coding",
            model="codex",
            reasoning_effort="medium",
            max_turns=4,
            max_budget=0.0,
            yolo_mode=True,
        ),
        prompt_template=Path("prompts/continuous_extraction_fix.yaml"),
    )


def test_load_config_validates_pinned_production_model(tmp_path: Path) -> None:
    """Decision-grade extraction configs should reject production-model drift."""

    config_dir = tmp_path / "eval"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "continuous.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repo_root: ..",
                "runtime:",
                "  python_command: [./.venv/bin/python, -u]",
                "family:",
                "  name: grounded_named_endpoint_completeness",
                "  cases_file: eval/fixtures/musique_tkg_extraction_prompt_eval_cases.json",
                "  prompt_family: two_pass_entity_inventory",
                "  target_variant: grounded_entity_contract",
                "  production_model: gemini/gemini-2.5-flash-lite",
                "agent:",
                "  selection_task: coding",
                "prompt_template: prompts/continuous_extraction_fix.yaml",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(config_path)


def test_load_config_resolves_repo_root_relative_to_config_file(tmp_path: Path) -> None:
    """Config loading should not depend on the launch cwd for repo-root resolution."""

    config_dir = tmp_path / "eval"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "continuous.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repo_root: ..",
                "runtime:",
                "  python_command: [./.venv/bin/python, -u]",
                "family:",
                "  name: grounded_named_endpoint_completeness",
                "  cases_file: eval/fixtures/musique_tkg_extraction_prompt_eval_cases.json",
                "  prompt_family: two_pass_entity_inventory",
                "  target_variant: grounded_entity_contract",
                "  production_model: gemini/gemini-2.5-flash",
                "agent:",
                "  selection_task: coding",
                "prompt_template: prompts/continuous_extraction_fix.yaml",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.repo_root == tmp_path.resolve()


def test_extract_variant_mean_score_reads_prompt_eval_output_json(tmp_path: Path) -> None:
    """The supervisor should parse the exact variant score it gates on."""

    artifact_path = tmp_path / "result.json"
    _write_prompt_eval_artifact(
        artifact_path,
        variant_name="grounded_entity_contract",
        mean_score=0.875,
    )

    assert extract_variant_mean_score(
        artifact_path,
        variant_name="grounded_entity_contract",
    ) == pytest.approx(0.875)


def test_improvement_gate_requires_strictly_higher_target_score() -> None:
    """The supervisor must reject flat or worse cycles."""

    assert has_strictly_improved(0.5, 0.5001) is True
    assert has_strictly_improved(0.5, 0.5) is False
    assert has_strictly_improved(0.5, 0.4) is False


def test_run_loop_reverts_no_improvement_and_persists_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A non-improving cycle should revert edits and leave a durable session record."""

    repo_root = tmp_path / "repo"
    _init_temp_repo(repo_root)
    config = _build_config(repo_root)

    # mock-ok: avoid manipulating real process signal handlers in a unit test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.install_signal_stop_flag",
        lambda: {"stop": False},
    )

    def fake_validation(*, session_dir: Path, label: str, **_: object) -> tuple[Path, Path]:
        """Emit deterministic prompt-eval artifacts for one supervisor cycle."""

        results_path = session_dir / f"{label}_prompt_eval.json"
        log_path = session_dir / f"{label}_prompt_eval.log"
        score = 0.7
        _write_prompt_eval_artifact(
            results_path,
            variant_name=config.family.target_variant,
            mean_score=score,
        )
        log_path.write_text(f"{label}\n", encoding="utf-8")
        return results_path, log_path

    async def fake_run_fix_agent(**_: object) -> str:
        """Simulate one agent edit against tracked repo content."""

        (repo_root / "tracked.txt").write_text("candidate change\n", encoding="utf-8")
        return "candidate change"

    # mock-ok: avoid real prompt_eval subprocesses; this test targets loop orchestration.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_prompt_eval_validation",
        fake_validation,
    )
    # mock-ok: avoid a real coding-agent call; the loop behavior after edits is the unit under test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_fix_agent",
        fake_run_fix_agent,
    )

    session_dir = run_loop(config, session_id="test-no-improvement", max_cycles=1)

    state = read_state(session_dir / "state.json")
    ledger_lines = (session_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ledger_event_types = [json.loads(line)["event_type"] for line in ledger_lines]

    assert state.baseline_results_file is not None
    assert state.latest_commit is None
    assert (repo_root / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert _run_git(repo_root, "status", "--short") == ""
    assert "baseline_recorded" in ledger_event_types
    assert "cycle_reverted_no_improvement" in ledger_event_types
    assert ledger_event_types[-1] == "session_stopped"


def test_run_loop_commits_verified_improvement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An improving cycle should create a real git commit and advance the baseline."""

    repo_root = tmp_path / "repo"
    _init_temp_repo(repo_root)
    config = _build_config(repo_root)

    # mock-ok: avoid manipulating real process signal handlers in a unit test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.install_signal_stop_flag",
        lambda: {"stop": False},
    )

    def fake_validation(*, session_dir: Path, label: str, **_: object) -> tuple[Path, Path]:
        """Emit an improving prompt-eval score on the cycle rerun."""

        results_path = session_dir / f"{label}_prompt_eval.json"
        log_path = session_dir / f"{label}_prompt_eval.log"
        score = 0.7 if label == "baseline" else 0.9
        _write_prompt_eval_artifact(
            results_path,
            variant_name=config.family.target_variant,
            mean_score=score,
        )
        log_path.write_text(f"{label}\n", encoding="utf-8")
        return results_path, log_path

    async def fake_run_fix_agent(**_: object) -> str:
        """Simulate one agent edit that should survive a verified improvement."""

        (repo_root / "tracked.txt").write_text("improved\n", encoding="utf-8")
        return "improved"

    # mock-ok: avoid real prompt_eval subprocesses; this test targets supervisor gating.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_prompt_eval_validation",
        fake_validation,
    )
    # mock-ok: avoid a real coding-agent call; commit behavior is the unit under test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_fix_agent",
        fake_run_fix_agent,
    )

    session_dir = run_loop(config, session_id="test-improvement", max_cycles=1)

    state = read_state(session_dir / "state.json")
    ledger_lines = (session_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ledger_event_types = [json.loads(line)["event_type"] for line in ledger_lines]

    assert state.latest_commit is not None
    assert state.baseline_results_file is not None
    assert state.baseline_results_file.endswith("cycle_0001_prompt_eval.json")
    assert (repo_root / "tracked.txt").read_text(encoding="utf-8") == "improved\n"
    assert _run_git(repo_root, "status", "--short") == ""
    assert int(_run_git(repo_root, "rev-list", "--count", "HEAD")) == 2
    assert "verified_commit_created" in ledger_event_types
