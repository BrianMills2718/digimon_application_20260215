"""Unit tests for the extraction-iteration supervisor thin slice."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode
from eval.extraction_prompt_eval import DEFAULT_CASES_PATH
from eval.run_extraction_iteration_supervisor import (
    AgentConfig,
    ExtractionIterationConfig,
    FamilyCaseRoleIndex,
    FamilyConfig,
    ImprovementDecision,
    RuntimeConfig,
    SmokeBuildConfig,
    VariantScoreSnapshot,
    build_smoke_build_command,
    evaluate_improvement,
    expected_smoke_artifact_paths,
    extract_variant_mean_score,
    extract_variant_score_snapshot,
    has_strictly_improved,
    load_family_case_role_index,
    load_config,
    read_state,
    run_loop,
    validate_agent_runtime_dependencies,
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


def _write_prompt_eval_artifact(
    path: Path,
    *,
    variant_name: str,
    mean_score: float,
    trial_scores: dict[str, float] | None = None,
) -> None:
    """Write the smallest prompt-eval JSON payload the supervisor needs to read."""

    scored_trials = trial_scores or {"case_target": mean_score}

    payload = {
        "experiment": {
            "summary": {
                variant_name: {
                    "mean_score": mean_score,
                }
            },
            "trials": [
                {
                    "variant_name": variant_name,
                    "input_id": input_id,
                    "replicate": 0,
                    "output": "",
                    "score": score,
                    "cost": 0.0,
                    "latency_ms": 0.0,
                    "tokens_used": 0,
                    "error": None,
                }
                for input_id, score in scored_trials.items()
            ],
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_cases_fixture(
    path: Path,
    *,
    roles_by_case_id: dict[str, str],
) -> None:
    """Write a minimal frozen-case fixture for supervisor role-index tests."""

    path.parent.mkdir(parents=True, exist_ok=True)
    cases = [
        {
            "id": case_id,
            "source_doc_id": 1,
            "title": case_id,
            "focus": case_id,
            "failure_family": "grounded_named_endpoint_completeness",
            "case_role": role,
            "content": f"content for {case_id}",
            "expected": {
                "min_valid_entities": 1,
                "min_valid_relationships": 0,
            },
        }
        for case_id, role in roles_by_case_id.items()
    ]
    path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")


def _init_temp_repo(repo_root: Path) -> None:
    """Create a small real git repo for supervisor loop tests."""

    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".gitignore").write_text("results/\n", encoding="utf-8")
    (repo_root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _write_cases_fixture(
        repo_root / "eval/fixtures/test_cases.json",
        roles_by_case_id={
            "case_target": "target",
            "case_sentinel": "sentinel",
        },
    )
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
    subprocess.run(
        ["git", "add", ".gitignore", "tracked.txt", "eval/fixtures/test_cases.json"],
        cwd=str(repo_root),
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial state"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )


def _build_config(
    repo_root: Path,
    *,
    smoke_build: SmokeBuildConfig | None = None,
) -> ExtractionIterationConfig:
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
            cases_file=Path("eval/fixtures/test_cases.json"),
            prompt_family="two_pass_entity_inventory",
            target_variant="grounded_entity_contract",
            production_model="gemini/gemini-2.5-flash",
            n_runs=1,
            comparison_method="paired_t",
        ),
        agent=AgentConfig(
            selection_task="code_generation",
            model="codex",
            reasoning_effort="medium",
            max_turns=4,
            max_budget=0.0,
            yolo_mode=True,
        ),
        smoke_build=smoke_build,
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


def test_agent_config_normalizes_coding_task_alias() -> None:
    """Historical supervisor task aliases should map to llm_client's canonical task names."""

    config = AgentConfig(selection_task="coding")

    assert config.selection_task == "code_generation"


def test_validate_agent_runtime_dependencies_rejects_missing_codex_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Codex-backed supervisor configs should fail before spending prompt-eval budget."""

    config = _build_config(
        tmp_path,
        smoke_build=SmokeBuildConfig(
            source_dataset="MuSiQue",
            artifact_dataset_name="MuSiQue_supervisor_smoke",
            graph_profile=GraphProfile.TKG,
            working_dir=Path("results"),
            required_artifacts=[
                Path("er_graph/nx_data.graphml"),
            ],
        ),
    ).model_copy(
        update={
            "agent": AgentConfig(
                selection_task="code_generation",
                model="codex",
                reasoning_effort="medium",
                max_turns=4,
                max_budget=0.0,
                yolo_mode=True,
            )
        }
    )

    # mock-ok: exercise the supervisor preflight path without requiring the real SDK layout.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.importlib.util.find_spec",
        lambda name: None if name == "openai_codex_sdk" else object(),
    )

    with pytest.raises(RuntimeError, match="requires the Codex SDK"):
        validate_agent_runtime_dependencies(config)


def test_validate_agent_runtime_dependencies_rejects_non_agent_model(tmp_path: Path) -> None:
    """The supervisor should fail before baseline validation when the fix lane cannot edit code."""

    config = _build_config(
        tmp_path,
        smoke_build=SmokeBuildConfig(
            source_dataset="MuSiQue",
            artifact_dataset_name="MuSiQue_supervisor_smoke",
            graph_profile=GraphProfile.TKG,
            working_dir=Path("results"),
            required_artifacts=[
                Path("er_graph/nx_data.graphml"),
            ],
        ),
    ).model_copy(
        update={
            "agent": AgentConfig(
                selection_task="code_generation",
                model="gpt-5.2-pro",
                reasoning_effort="medium",
                max_turns=4,
                max_budget=0.0,
                yolo_mode=True,
            )
        }
    )

    with pytest.raises(RuntimeError, match="requires an agent SDK model"):
        validate_agent_runtime_dependencies(config)


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


def test_extract_variant_score_snapshot_reads_role_scoped_scores(tmp_path: Path) -> None:
    """The supervisor should parse target and sentinel scores from prompt-eval trials."""

    artifact_path = tmp_path / "result.json"
    cases_path = tmp_path / "cases.json"
    _write_cases_fixture(
        cases_path,
        roles_by_case_id={
            "case_target": "target",
            "case_sentinel": "sentinel",
        },
    )
    _write_prompt_eval_artifact(
        artifact_path,
        variant_name="grounded_entity_contract",
        mean_score=0.8,
        trial_scores={
            "case_target": 0.9,
            "case_sentinel": 0.7,
        },
    )

    snapshot = extract_variant_score_snapshot(
        artifact_path,
        variant_name="grounded_entity_contract",
        case_roles=load_family_case_role_index(
            cases_path,
            failure_family="grounded_named_endpoint_completeness",
        ),
    )

    assert snapshot.promotion_basis == "target"
    assert snapshot.target_mean_score == pytest.approx(0.9)
    assert snapshot.sentinel_mean_score == pytest.approx(0.7)
    assert snapshot.overall_mean_score == pytest.approx(0.8)


def test_load_family_case_role_index_reads_grounded_target_and_sentinel_roles() -> None:
    """The grounded-endpoint family should expose one target and one protected sentinel."""

    case_roles = load_family_case_role_index(
        DEFAULT_CASES_PATH,
        failure_family="grounded_named_endpoint_completeness",
    )

    assert case_roles.target_case_ids == ["musique_doc_5_grounded_medical_leave"]
    assert case_roles.sentinel_case_ids == ["musique_doc_9_grounded_silver_ball"]


def test_build_smoke_build_command_respects_typed_config(tmp_path: Path) -> None:
    """The supervisor should emit the explicit prebuild contract from typed config."""

    config = _build_config(
        tmp_path,
        smoke_build=SmokeBuildConfig(
            source_dataset="MuSiQue",
            artifact_dataset_name="MuSiQue_supervisor_smoke",
            graph_profile=GraphProfile.TKG,
            schema_mode=GraphSchemaMode.OPEN,
            force_rebuild=True,
            chunk_limit=10,
            strict_extraction_slot_discipline=True,
            two_pass_extraction=True,
            prefer_grounded_named_entities=True,
            lane_policy="pure",
            skip_entity_vdb=True,
            skip_relationship_vdb=True,
            working_dir=Path("results"),
            required_artifacts=[
                Path("er_graph/nx_data.graphml"),
                Path("er_graph/graph_build_manifest.json"),
            ],
        ),
    )

    cmd = build_smoke_build_command(repo_root=tmp_path, config=config)

    assert cmd == [
        "./.venv/bin/python",
        "-u",
        str(tmp_path / "eval/prebuild_graph.py"),
        "MuSiQue",
        "--artifact-dataset-name",
        "MuSiQue_supervisor_smoke",
        "--graph-profile",
        "tkg",
        "--lane-policy",
        "pure",
        "--force-rebuild",
        "--schema-mode",
        "open",
        "--chunk-limit",
        "10",
        "--strict-extraction-slot-discipline",
        "--two-pass-extraction",
        "--prefer-grounded-named-entities",
        "--skip-entity-vdb",
        "--skip-relationship-vdb",
    ]


def test_expected_smoke_artifact_paths_use_working_dir_and_alias(tmp_path: Path) -> None:
    """Artifact checks should derive from the typed working-dir and namespace contract."""

    smoke_build = SmokeBuildConfig(
        source_dataset="MuSiQue",
        artifact_dataset_name="MuSiQue_supervisor_smoke",
        graph_profile=GraphProfile.TKG,
        working_dir=Path("tmp/results"),
        required_artifacts=[
            Path("er_graph/nx_data.graphml"),
            Path("er_graph/graph_build_manifest.json"),
        ],
    )

    artifact_paths = expected_smoke_artifact_paths(
        repo_root=tmp_path,
        smoke_build=smoke_build,
    )

    assert artifact_paths == [
        tmp_path / "tmp/results" / "MuSiQue_supervisor_smoke" / "er_graph/nx_data.graphml",
        tmp_path
        / "tmp/results"
        / "MuSiQue_supervisor_smoke"
        / "er_graph/graph_build_manifest.json",
    ]


def test_improvement_gate_requires_strictly_higher_target_score() -> None:
    """The supervisor must reject flat or worse cycles."""

    assert has_strictly_improved(0.5, 0.5001) is True
    assert has_strictly_improved(0.5, 0.5) is False
    assert has_strictly_improved(0.5, 0.4) is False


def test_verified_improvement_requires_target_gain_and_no_sentinel_regression() -> None:
    """Promotion should fail when sentinels regress, even if targets improve."""

    previous = VariantScoreSnapshot(
        overall_mean_score=0.7,
        promotion_mean_score=0.8,
        promotion_basis="target",
        target_mean_score=0.8,
        sentinel_mean_score=0.6,
        n_overall_trials=2,
        n_target_trials=1,
        n_sentinel_trials=1,
    )
    current = VariantScoreSnapshot(
        overall_mean_score=0.75,
        promotion_mean_score=0.9,
        promotion_basis="target",
        target_mean_score=0.9,
        sentinel_mean_score=0.5,
        n_overall_trials=2,
        n_target_trials=1,
        n_sentinel_trials=1,
    )

    decision = evaluate_improvement(previous, current)

    assert decision == ImprovementDecision(
        verified=False,
        promotion_improved=True,
        sentinel_non_regression=False,
    )


def test_verified_improvement_falls_back_to_overall_when_family_has_no_target_cases() -> None:
    """Families with only sentinels should use overall score as the promotion surface."""

    case_roles = FamilyCaseRoleIndex(
        target_case_ids=[],
        sentinel_case_ids=[
            "synthetic_sentinel_a",
            "synthetic_sentinel_b",
        ],
    )
    previous = VariantScoreSnapshot(
        overall_mean_score=0.6,
        promotion_mean_score=0.6,
        promotion_basis="overall",
        target_mean_score=None,
        sentinel_mean_score=0.6,
        n_overall_trials=2,
        n_target_trials=0,
        n_sentinel_trials=2,
    )
    current = VariantScoreSnapshot(
        overall_mean_score=0.7,
        promotion_mean_score=0.7,
        promotion_basis="overall",
        target_mean_score=None,
        sentinel_mean_score=0.7,
        n_overall_trials=2,
        n_target_trials=0,
        n_sentinel_trials=2,
    )

    decision = evaluate_improvement(previous, current)

    assert case_roles.target_case_ids == []
    assert case_roles.sentinel_case_ids == [
        "synthetic_sentinel_a",
        "synthetic_sentinel_b",
    ]
    assert decision.verified is True
    assert decision.promotion_improved is True
    assert decision.sentinel_non_regression is True


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
    # mock-ok: this test isolates loop behavior after edits, not SDK dependency wiring.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.validate_agent_runtime_dependencies",
        lambda config: None,
    )

    def fake_validation(*, session_dir: Path, label: str, **_: object) -> tuple[Path, Path]:
        """Emit deterministic prompt-eval artifacts for one supervisor cycle."""

        results_path = session_dir / f"{label}_prompt_eval.json"
        log_path = session_dir / f"{label}_prompt_eval.log"
        _write_prompt_eval_artifact(
            results_path,
            variant_name=config.family.target_variant,
            mean_score=0.7,
            trial_scores={
                "case_target": 0.7,
                "case_sentinel": 0.7,
            },
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
    assert "cycle_reverted_gate_failure" in ledger_event_types
    assert ledger_event_types[-1] == "session_stopped"


def test_run_loop_reverts_when_sentinel_regresses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A target gain should still be rejected when the sentinel score drops."""

    repo_root = tmp_path / "repo"
    _init_temp_repo(repo_root)
    config = _build_config(repo_root)

    # mock-ok: avoid manipulating real process signal handlers in a unit test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.install_signal_stop_flag",
        lambda: {"stop": False},
    )
    # mock-ok: this test isolates supervisor gating, not SDK dependency wiring.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.validate_agent_runtime_dependencies",
        lambda config: None,
    )

    def fake_validation(*, session_dir: Path, label: str, **_: object) -> tuple[Path, Path]:
        """Emit a target improvement that still regresses the protected sentinel."""

        results_path = session_dir / f"{label}_prompt_eval.json"
        log_path = session_dir / f"{label}_prompt_eval.log"
        trial_scores = (
            {"case_target": 0.6, "case_sentinel": 0.8}
            if label == "baseline"
            else {"case_target": 0.9, "case_sentinel": 0.4}
        )
        _write_prompt_eval_artifact(
            results_path,
            variant_name=config.family.target_variant,
            mean_score=sum(trial_scores.values()) / len(trial_scores),
            trial_scores=trial_scores,
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
    ledger_events = [json.loads(line) for line in ledger_lines]
    ledger_event_types = [event["event_type"] for event in ledger_events]

    validation_event = next(
        event for event in ledger_events if event["event_type"] == "validation_completed"
    )

    assert state.latest_commit is None
    assert (repo_root / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert _run_git(repo_root, "status", "--short") == ""
    assert validation_event["promotion_improved"] is True
    assert validation_event["sentinel_non_regression"] is False
    assert "cycle_reverted_gate_failure" in ledger_event_types


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
    # mock-ok: this test isolates commit behavior, not SDK dependency wiring.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.validate_agent_runtime_dependencies",
        lambda config: None,
    )

    def fake_validation(*, session_dir: Path, label: str, **_: object) -> tuple[Path, Path]:
        """Emit a target improvement while holding the sentinel steady."""

        results_path = session_dir / f"{label}_prompt_eval.json"
        log_path = session_dir / f"{label}_prompt_eval.log"
        trial_scores = (
            {"case_target": 0.6, "case_sentinel": 0.8}
            if label == "baseline"
            else {"case_target": 0.9, "case_sentinel": 0.8}
        )
        _write_prompt_eval_artifact(
            results_path,
            variant_name=config.family.target_variant,
            mean_score=sum(trial_scores.values()) / len(trial_scores),
            trial_scores=trial_scores,
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

    session_dir = run_loop(config, session_id="test-commit", max_cycles=1)

    state = read_state(session_dir / "state.json")
    ledger_lines = (session_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ledger_events = [json.loads(line) for line in ledger_lines]
    ledger_event_types = [event["event_type"] for event in ledger_events]
    validation_event = next(
        event for event in ledger_events if event["event_type"] == "validation_completed"
    )

    assert state.latest_commit is not None
    assert state.baseline_results_file is not None
    assert state.baseline_results_file.endswith("cycle_0001_prompt_eval.json")
    assert (repo_root / "tracked.txt").read_text(encoding="utf-8") == "improved\n"
    assert _run_git(repo_root, "status", "--short") == ""
    assert int(_run_git(repo_root, "rev-list", "--count", "HEAD")) == 2
    assert validation_event["promotion_improved"] is True
    assert validation_event["sentinel_non_regression"] is True
    assert "verified_commit_created" in ledger_event_types


def test_run_loop_reverts_when_smoke_build_fails_after_prompt_eval_gain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prompt-eval improvement alone should not commit when the live smoke build fails."""

    repo_root = tmp_path / "repo"
    _init_temp_repo(repo_root)
    config = _build_config(
        repo_root,
        smoke_build=SmokeBuildConfig(
            source_dataset="MuSiQue",
            artifact_dataset_name="MuSiQue_supervisor_smoke",
            graph_profile=GraphProfile.TKG,
            chunk_limit=10,
            strict_extraction_slot_discipline=True,
            two_pass_extraction=True,
            prefer_grounded_named_entities=True,
            lane_policy="pure",
            skip_entity_vdb=True,
            skip_relationship_vdb=True,
            working_dir=Path("results"),
            required_artifacts=[
                Path("er_graph/nx_data.graphml"),
                Path("er_graph/graph_build_manifest.json"),
            ],
        ),
    )

    # mock-ok: avoid manipulating real process signal handlers in a unit test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.install_signal_stop_flag",
        lambda: {"stop": False},
    )
    # mock-ok: this test isolates smoke-gate failure handling, not SDK dependency wiring.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.validate_agent_runtime_dependencies",
        lambda config: None,
    )

    def fake_validation(*, session_dir: Path, label: str, **_: object) -> tuple[Path, Path]:
        """Emit a verified prompt-eval improvement so the smoke gate becomes decisive."""

        results_path = session_dir / f"{label}_prompt_eval.json"
        log_path = session_dir / f"{label}_prompt_eval.log"
        trial_scores = (
            {"case_target": 0.6, "case_sentinel": 0.8}
            if label == "baseline"
            else {"case_target": 0.9, "case_sentinel": 0.8}
        )
        _write_prompt_eval_artifact(
            results_path,
            variant_name=config.family.target_variant,
            mean_score=sum(trial_scores.values()) / len(trial_scores),
            trial_scores=trial_scores,
        )
        log_path.write_text(f"{label}\n", encoding="utf-8")
        return results_path, log_path

    async def fake_run_fix_agent(**_: object) -> str:
        """Simulate one improving edit that must still be reverted on smoke failure."""

        (repo_root / "tracked.txt").write_text("candidate change\n", encoding="utf-8")
        return "candidate change"

    def fake_run_smoke_build_validation(**_: object) -> object:
        """Force the live smoke gate to fail after prompt-eval success."""

        raise RuntimeError("smoke build failed")

    # mock-ok: avoid real prompt_eval subprocesses; this test targets supervisor orchestration.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_prompt_eval_validation",
        fake_validation,
    )
    # mock-ok: avoid a real coding-agent call; revert behavior is the unit under test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_fix_agent",
        fake_run_fix_agent,
    )
    # mock-ok: avoid a real prebuild run; smoke-gate failure handling is the unit under test.
    monkeypatch.setattr(
        "eval.run_extraction_iteration_supervisor.run_smoke_build_validation",
        fake_run_smoke_build_validation,
    )

    session_dir = run_loop(config, session_id="test-smoke-failure", max_cycles=1)

    state = read_state(session_dir / "state.json")
    ledger_lines = (session_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ledger_event_types = [json.loads(line)["event_type"] for line in ledger_lines]

    assert state.latest_commit is None
    assert (repo_root / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert _run_git(repo_root, "status", "--short") == ""
    assert "validation_completed" in ledger_event_types
    assert "cycle_smoke_build_error" in ledger_event_types
    assert "verified_commit_created" not in ledger_event_types
