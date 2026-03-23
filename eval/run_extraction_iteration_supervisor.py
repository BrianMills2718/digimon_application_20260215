#!/usr/bin/env python3
"""Run a bounded extraction-quality improvement supervisor for one failure family.

This supervisor is the active-repo successor to the older DIGIMON autoloop.
It intentionally narrows scope to the current extraction-quality critical path:

1. baseline one failure-family prompt-eval gate
2. invoke a coding agent against that family context
3. rerun the same gate
4. optionally prove the live graph-build path still works on a smoke slice
5. revert on failure, commit on verified improvement

The current architecture still stops short of full benchmark reruns. The goal
of this thin slice is to promote only those changes that improve the pinned
prompt-eval lane and keep the bounded live build path healthy.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shlex
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode
from eval.extraction_prompt_eval import (
    PROMPT_FAMILY_ONE_PASS,
    PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY,
    filter_extraction_prompt_eval_cases,
    load_extraction_prompt_eval_cases,
)
from llm_client import acall_llm, get_model, render_prompt


class RuntimeConfig(BaseModel):
    """Runtime controls for the extraction supervisor process."""

    python_command: list[str] = Field(default_factory=lambda: ["python", "-u"])
    duration_hours: float = 24.0
    validation_timeout_seconds: int = 7200
    agent_timeout_seconds: int = 1800
    sleep_on_noop_seconds: int = 30
    results_root: Path = Path("results/continuous_extraction")


class FamilyConfig(BaseModel):
    """Configuration for the failure family currently under active repair."""

    name: str
    cases_file: Path
    prompt_family: Literal[
        PROMPT_FAMILY_ONE_PASS,
        PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY,
    ] = PROMPT_FAMILY_TWO_PASS_ENTITY_INVENTORY
    target_variant: str = "grounded_entity_contract"
    promotion_dimension: str | None = None
    production_model: str = "gemini/gemini-2.5-flash"
    n_runs: int = 1
    comparison_method: Literal["paired_t", "bootstrap"] = "paired_t"

    @field_validator("production_model")
    @classmethod
    def _validate_pinned_production_model(cls, value: str) -> str:
        """Keep decision-grade extraction validation on the approved model lane."""

        normalized = value.strip()
        if normalized != "gemini/gemini-2.5-flash":
            raise ValueError(
                "Extraction supervisor production_model must stay pinned to "
                "'gemini/gemini-2.5-flash' for decision-grade comparisons."
            )
        return normalized


class AgentConfig(BaseModel):
    """Coding-agent settings for one bounded extraction-family fix attempt."""

    selection_task: str = "code_generation"
    model: str | None = None
    reasoning_effort: str | None = None
    max_turns: int = 24
    max_budget: float = 0.0
    yolo_mode: bool = True

    @field_validator("selection_task")
    @classmethod
    def _normalize_selection_task(cls, value: str) -> str:
        """Map historical supervisor task aliases onto llm_client's canonical names."""

        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        alias_map = {
            "coding": "code_generation",
            "codegen": "code_generation",
        }
        return alias_map.get(normalized, normalized)


class SmokeBuildConfig(BaseModel):
    """Typed operational smoke-build contract run before supervisor promotion."""

    source_dataset: str
    artifact_dataset_name: str
    graph_profile: GraphProfile
    schema_mode: GraphSchemaMode | None = None
    force_rebuild: bool = True
    chunk_limit: int | None = None
    strict_extraction_slot_discipline: bool = False
    two_pass_extraction: bool = False
    prefer_grounded_named_entities: bool = False
    lane_policy: Literal["pure", "reliability"] = "pure"
    skip_entity_vdb: bool = True
    skip_relationship_vdb: bool = True
    working_dir: Path = Path("results")
    required_artifacts: list[Path] = Field(default_factory=list)

    @field_validator("graph_profile")
    @classmethod
    def _validate_entity_graph_profile(cls, value: GraphProfile) -> GraphProfile:
        """Restrict smoke builds to the entity-graph profiles supported by prebuild."""

        if value not in {GraphProfile.KG, GraphProfile.TKG, GraphProfile.RKG}:
            raise ValueError(
                "Smoke-build graph_profile must be one of KG, TKG, or RKG "
                "to match eval/prebuild_graph.py."
            )
        return value

    @field_validator("chunk_limit")
    @classmethod
    def _validate_chunk_limit(cls, value: int | None) -> int | None:
        """Require a positive chunk limit when the smoke gate narrows the corpus slice."""

        if value is not None and value < 1:
            raise ValueError("Smoke-build chunk_limit must be at least 1 when provided.")
        return value

    @field_validator("working_dir")
    @classmethod
    def _validate_relative_working_dir(cls, value: Path) -> Path:
        """Keep smoke-build artifact roots repo-relative and explicit."""

        if value.is_absolute():
            raise ValueError("Smoke-build working_dir must be relative to repo_root.")
        return value

    @field_validator("required_artifacts")
    @classmethod
    def _validate_required_artifacts(cls, value: list[Path]) -> list[Path]:
        """Require explicit relative artifact checks rooted under the artifact namespace."""

        if not value:
            raise ValueError("Smoke-build required_artifacts must not be empty.")
        for artifact_path in value:
            if artifact_path.is_absolute():
                raise ValueError(
                    "Smoke-build required_artifacts must be relative to "
                    "working_dir/artifact_dataset_name."
                )
        return value


class SmokeBuildValidationResult(BaseModel):
    """Operational proof returned by a successful smoke-build gate."""

    log_file: Path
    checked_artifact_paths: list[Path]


class ExtractionIterationConfig(BaseModel):
    """Top-level typed configuration for the extraction supervisor."""

    repo_root: Path = Path(".")
    runtime: RuntimeConfig
    family: FamilyConfig
    agent: AgentConfig
    smoke_build: SmokeBuildConfig | None = None
    prompt_template: Path


class LoopState(BaseModel):
    """Durable supervisor state persisted after each meaningful cycle edge."""

    session_id: str
    started_at: str
    cycle_index: int = 0
    baseline_results_file: str | None = None
    baseline_log_file: str | None = None
    latest_commit: str | None = None


class FamilyCaseRoleIndex(BaseModel):
    """Frozen-case role metadata for one failure-family supervisor slice."""

    target_case_ids: list[str] = Field(default_factory=list)
    sentinel_case_ids: list[str] = Field(default_factory=list)


class VariantScoreSnapshot(BaseModel):
    """Role-aware score snapshot extracted from one prompt-eval artifact."""

    overall_mean_score: float
    promotion_mean_score: float
    promotion_basis: Literal["target", "overall", "target_dimension"]
    promotion_dimension: str | None = None
    target_mean_score: float | None = None
    sentinel_mean_score: float | None = None
    n_overall_trials: int
    n_target_trials: int = 0
    n_sentinel_trials: int = 0


class ImprovementDecision(BaseModel):
    """Decision payload for whether a supervisor cycle earned promotion."""

    verified: bool
    promotion_improved: bool
    sentinel_non_regression: bool


def _utc_now() -> datetime:
    """Return the current UTC time for durable session bookkeeping."""

    return datetime.now(timezone.utc)


def _utc_stamp() -> str:
    """Return a compact UTC timestamp suitable for session identifiers."""

    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _repo_path(repo_root: Path, relative_path: str | Path) -> Path:
    """Resolve a repo-relative path while preserving already-absolute inputs."""

    candidate = Path(relative_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def load_config(config_path: Path) -> ExtractionIterationConfig:
    """Load config and resolve the repo root relative to the config file."""

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"Extraction supervisor config must be a mapping, got {type(raw).__name__}"
        )
    config = ExtractionIterationConfig.model_validate(raw)
    resolved_repo_root = _repo_path(config_path.parent.resolve(), config.repo_root)
    return config.model_copy(update={"repo_root": resolved_repo_root})


def write_state(path: Path, state: LoopState) -> None:
    """Persist durable loop state as JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_state(path: Path) -> LoopState:
    """Load a previously persisted loop state file."""

    return LoopState.model_validate(json.loads(path.read_text(encoding="utf-8")))


def append_ledger_event(
    ledger_path: Path,
    *,
    event_type: str,
    cycle: int,
    **payload: Any,
) -> None:
    """Append one structured event to the supervisor JSONL ledger."""

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": _utc_now().isoformat(),
        "event_type": event_type,
        "cycle": cycle,
        **payload,
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def describe_exception(exc: BaseException) -> dict[str, str]:
    """Return stable exception details for ledger logging."""

    message = str(exc).strip()
    return {
        "error": message or repr(exc),
        "error_type": type(exc).__name__,
    }


def git_output(repo_root: Path, *args: str) -> str:
    """Run one git command and return trimmed stdout."""

    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def git_has_changes(repo_root: Path) -> bool:
    """Return whether the current worktree has staged or unstaged changes."""

    return bool(git_output(repo_root, "status", "--short"))


def revert_worktree(repo_root: Path) -> None:
    """Restore the worktree to HEAD after an unhelpful supervisor cycle."""

    subprocess.run(
        ["git", "restore", "--staged", "--worktree", "."],
        cwd=str(repo_root),
        check=True,
    )
    subprocess.run(["git", "clean", "-fd"], cwd=str(repo_root), check=True)


def install_signal_stop_flag() -> dict[str, bool]:
    """Install SIGINT/SIGTERM handling for graceful long-run shutdown."""

    state = {"stop": False}

    def _handler(_signum: int, _frame: Any) -> None:
        state["stop"] = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    return state


def run_logged_command(
    *,
    cmd: list[str],
    cwd: Path,
    log_path: Path,
    timeout_seconds: int,
) -> None:
    """Run one subprocess while mirroring stdout/stderr into a durable log file."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(shlex.quote(part) for part in cmd)}\n\n")
        handle.flush()
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(cwd),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=timeout_seconds,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            handle.write(
                f"\nCOMMAND TIMEOUT after {timeout_seconds}s: "
                f"{' '.join(shlex.quote(part) for part in cmd)}\n"
            )
            raise RuntimeError(
                f"Command timed out after {timeout_seconds}s (see {log_path})"
            ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode} (see {log_path})"
        )


def extract_variant_mean_score(results_path: Path, *, variant_name: str) -> float:
    """Extract one variant mean score from an extraction prompt-eval JSON artifact."""

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    experiment = payload.get("experiment")
    if not isinstance(experiment, dict):
        raise RuntimeError(f"Prompt-eval artifact missing experiment payload: {results_path}")
    summary = experiment.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"Prompt-eval artifact missing summary payload: {results_path}")
    variant_summary = summary.get(variant_name)
    if not isinstance(variant_summary, dict):
        raise RuntimeError(
            f"Prompt-eval artifact missing variant {variant_name!r}: {results_path}"
        )
    score = variant_summary.get("mean_score")
    if score is None:
        raise RuntimeError(
            f"Prompt-eval artifact missing mean_score for variant {variant_name!r}: {results_path}"
        )
    return float(score)


def load_family_case_role_index(
    cases_path: Path,
    *,
    failure_family: str,
) -> FamilyCaseRoleIndex:
    """Load the frozen case-role metadata for one failure family."""

    cases = filter_extraction_prompt_eval_cases(
        load_extraction_prompt_eval_cases(cases_path),
        failure_family=failure_family,
    )
    if not cases:
        raise RuntimeError(
            "Extraction supervisor could not find any frozen cases for failure family "
            f"{failure_family!r} in {cases_path}"
        )
    return FamilyCaseRoleIndex(
        target_case_ids=sorted(case.id for case in cases if case.case_role == "target"),
        sentinel_case_ids=sorted(
            case.id for case in cases if case.case_role == "sentinel"
        ),
    )


def _extract_matching_trial_scores(
    *,
    trials_payload: list[object],
    variant_name: str,
    input_ids: set[str] | None = None,
) -> list[float]:
    """Collect scored trial values for one variant and optional input-id subset."""

    matched_scores: list[float] = []
    for raw_trial in trials_payload:
        if not isinstance(raw_trial, dict):
            continue
        if raw_trial.get("variant_name") != variant_name:
            continue
        input_id = raw_trial.get("input_id")
        if input_ids is not None and input_id not in input_ids:
            continue
        score = raw_trial.get("score")
        if score is None:
            continue
        matched_scores.append(float(score))
    return matched_scores


def _extract_matching_dimension_scores(
    *,
    trials_payload: list[object],
    variant_name: str,
    dimension_name: str,
    input_ids: set[str] | None = None,
) -> list[float]:
    """Collect one named dimension score for a variant and optional case subset."""

    matched_scores: list[float] = []
    for raw_trial in trials_payload:
        if not isinstance(raw_trial, dict):
            continue
        if raw_trial.get("variant_name") != variant_name:
            continue
        input_id = raw_trial.get("input_id")
        if input_ids is not None and input_id not in input_ids:
            continue
        dimension_scores = raw_trial.get("dimension_scores")
        if not isinstance(dimension_scores, dict):
            continue
        score = dimension_scores.get(dimension_name)
        if score is None:
            continue
        matched_scores.append(float(score))
    return matched_scores


def extract_variant_score_snapshot(
    results_path: Path,
    *,
    variant_name: str,
    case_roles: FamilyCaseRoleIndex,
    promotion_dimension: str | None = None,
) -> VariantScoreSnapshot:
    """Extract role-aware variant scores from one prompt-eval JSON artifact."""

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    experiment = payload.get("experiment")
    if not isinstance(experiment, dict):
        raise RuntimeError(f"Prompt-eval artifact missing experiment payload: {results_path}")
    trials_payload = experiment.get("trials")
    if not isinstance(trials_payload, list):
        raise RuntimeError(f"Prompt-eval artifact missing trial payload: {results_path}")

    overall_scores = _extract_matching_trial_scores(
        trials_payload=trials_payload,
        variant_name=variant_name,
    )
    if not overall_scores:
        raise RuntimeError(
            f"Prompt-eval artifact missing scored trials for variant {variant_name!r}: {results_path}"
        )

    target_ids = set(case_roles.target_case_ids)
    sentinel_ids = set(case_roles.sentinel_case_ids)
    target_scores = (
        _extract_matching_trial_scores(
            trials_payload=trials_payload,
            variant_name=variant_name,
            input_ids=target_ids,
        )
        if target_ids
        else []
    )
    sentinel_scores = (
        _extract_matching_trial_scores(
            trials_payload=trials_payload,
            variant_name=variant_name,
            input_ids=sentinel_ids,
        )
        if sentinel_ids
        else []
    )

    if target_ids and not target_scores:
        raise RuntimeError(
            "Prompt-eval artifact missing scored target trials for variant "
            f"{variant_name!r}: {results_path}"
        )
    if sentinel_ids and not sentinel_scores:
        raise RuntimeError(
            "Prompt-eval artifact missing scored sentinel trials for variant "
            f"{variant_name!r}: {results_path}"
        )

    target_mean_score = statistics.mean(target_scores) if target_scores else None
    sentinel_mean_score = (
        statistics.mean(sentinel_scores) if sentinel_scores else None
    )
    promotion_basis: Literal["target", "overall", "target_dimension"]
    if promotion_dimension is not None:
        if not target_ids:
            raise RuntimeError(
                "Configured promotion_dimension requires at least one target case."
            )
        promotion_dimension_scores = _extract_matching_dimension_scores(
            trials_payload=trials_payload,
            variant_name=variant_name,
            dimension_name=promotion_dimension,
            input_ids=target_ids,
        )
        if not promotion_dimension_scores:
            raise RuntimeError(
                "Prompt-eval artifact missing target-case dimension scores for "
                f"{promotion_dimension!r} on variant {variant_name!r}: {results_path}"
            )
        promotion_basis = "target_dimension"
        promotion_mean_score = statistics.mean(promotion_dimension_scores)
    else:
        promotion_basis = "target" if target_mean_score is not None else "overall"
        promotion_mean_score = (
            target_mean_score if target_mean_score is not None else statistics.mean(overall_scores)
        )

    return VariantScoreSnapshot(
        overall_mean_score=statistics.mean(overall_scores),
        promotion_mean_score=promotion_mean_score,
        promotion_basis=promotion_basis,
        promotion_dimension=promotion_dimension,
        target_mean_score=target_mean_score,
        sentinel_mean_score=sentinel_mean_score,
        n_overall_trials=len(overall_scores),
        n_target_trials=len(target_scores),
        n_sentinel_trials=len(sentinel_scores),
    )


def has_strictly_improved(previous_score: float, current_score: float) -> bool:
    """Return whether the current gate score is strictly better than baseline."""

    return current_score > previous_score


def evaluate_improvement(
    previous: VariantScoreSnapshot,
    current: VariantScoreSnapshot,
) -> ImprovementDecision:
    """Evaluate whether a supervisor cycle can be promoted."""

    promotion_improved = has_strictly_improved(
        previous.promotion_mean_score,
        current.promotion_mean_score,
    )
    sentinel_non_regression = True
    if previous.sentinel_mean_score is not None:
        if current.sentinel_mean_score is None:
            raise RuntimeError(
                "Current score snapshot is missing sentinel scores required by the baseline gate."
            )
        sentinel_non_regression = (
            current.sentinel_mean_score >= previous.sentinel_mean_score
        )
    return ImprovementDecision(
        verified=promotion_improved and sentinel_non_regression,
        promotion_improved=promotion_improved,
        sentinel_non_regression=sentinel_non_regression,
    )


def snapshot_ledger_fields(
    snapshot: VariantScoreSnapshot,
    *,
    prefix: str,
) -> dict[str, float | int | str | None]:
    """Render compact ledger fields for one score snapshot."""

    return {
        f"{prefix}_overall_score": snapshot.overall_mean_score,
        f"{prefix}_promotion_score": snapshot.promotion_mean_score,
        f"{prefix}_promotion_basis": snapshot.promotion_basis,
        f"{prefix}_promotion_dimension": snapshot.promotion_dimension,
        f"{prefix}_target_score": snapshot.target_mean_score,
        f"{prefix}_sentinel_score": snapshot.sentinel_mean_score,
        f"{prefix}_overall_trials": snapshot.n_overall_trials,
        f"{prefix}_target_trials": snapshot.n_target_trials,
        f"{prefix}_sentinel_trials": snapshot.n_sentinel_trials,
    }


def build_prompt_eval_command(
    *,
    repo_root: Path,
    config: ExtractionIterationConfig,
    output_json: Path,
) -> list[str]:
    """Build the family-scoped prompt-eval command for one supervisor cycle."""

    family = config.family
    return [
        *config.runtime.python_command,
        str(_repo_path(repo_root, "eval/extraction_prompt_eval.py")),
        "--cases-file",
        str(_repo_path(repo_root, family.cases_file)),
        "--failure-family",
        family.name,
        "--prompt-family",
        family.prompt_family,
        "--model",
        family.production_model,
        "--n-runs",
        str(family.n_runs),
        "--comparison-method",
        family.comparison_method,
        "--output-json",
        str(output_json),
    ]


def run_prompt_eval_validation(
    *,
    repo_root: Path,
    config: ExtractionIterationConfig,
    session_dir: Path,
    label: str,
) -> tuple[Path, Path]:
    """Run one family-scoped prompt-eval validation command and return its artifacts."""

    results_path = session_dir / f"{label}_prompt_eval.json"
    log_path = session_dir / f"{label}_prompt_eval.log"
    run_logged_command(
        cmd=build_prompt_eval_command(
            repo_root=repo_root,
            config=config,
            output_json=results_path,
        ),
        cwd=repo_root,
        log_path=log_path,
        timeout_seconds=config.runtime.validation_timeout_seconds,
    )
    return results_path, log_path


def _model_uses_codex_sdk(model: str) -> bool:
    """Return whether a configured agent model depends on the Codex SDK transport."""

    normalized = model.strip().lower()
    return normalized == "codex" or normalized.startswith("codex/") or normalized.startswith(
        "codex-"
    )


def _model_uses_agent_sdk(model: str) -> bool:
    """Return whether a model routes through an agent SDK instead of plain litellm."""

    normalized = model.strip().lower()
    return (
        _model_uses_codex_sdk(model)
        or normalized == "claude-code"
        or normalized.startswith("claude-code/")
        or normalized == "openai-agents"
        or normalized.startswith("openai-agents/")
    )


def resolve_supervisor_agent_model(config: ExtractionIterationConfig) -> str:
    """Resolve the exact model name the supervisor will use for its fix-agent lane."""

    return config.agent.model or get_model(config.agent.selection_task)


def validate_agent_runtime_dependencies(config: ExtractionIterationConfig) -> None:
    """Fail early when the configured agent lane requires missing runtime dependencies."""

    model = resolve_supervisor_agent_model(config)
    if not _model_uses_agent_sdk(model):
        raise RuntimeError(
            "Extraction supervisor fix-agent lane requires an agent SDK model "
            "because it passes working_directory, yolo_mode, and max_turns for "
            f"live repo edits. Resolved model {model!r} is not agent-SDK-backed."
        )
    if _model_uses_codex_sdk(model) and importlib.util.find_spec("openai_codex_sdk") is None:
        raise RuntimeError(
            "Extraction supervisor agent.model requires the Codex SDK, but "
            "openai_codex_sdk is not installed in this repo venv. Install "
            "with './.venv/bin/pip install -e ~/projects/llm_client[codex]' "
            "or choose a non-codex supervisor agent model."
        )


def build_smoke_build_command(
    *,
    repo_root: Path,
    config: ExtractionIterationConfig,
) -> list[str]:
    """Build the prebuild-graph smoke command from the typed supervisor contract."""

    smoke_build = config.smoke_build
    if smoke_build is None:
        raise RuntimeError("Cannot build a smoke-build command without smoke_build config.")

    cmd = [
        *config.runtime.python_command,
        str(_repo_path(repo_root, "eval/prebuild_graph.py")),
        smoke_build.source_dataset,
        "--artifact-dataset-name",
        smoke_build.artifact_dataset_name,
        "--graph-profile",
        smoke_build.graph_profile.value.lower(),
        "--lane-policy",
        smoke_build.lane_policy,
    ]
    if smoke_build.force_rebuild:
        cmd.append("--force-rebuild")
    if smoke_build.schema_mode is not None:
        cmd.extend(["--schema-mode", smoke_build.schema_mode.value])
    if smoke_build.chunk_limit is not None:
        cmd.extend(["--chunk-limit", str(smoke_build.chunk_limit)])
    if smoke_build.strict_extraction_slot_discipline:
        cmd.append("--strict-extraction-slot-discipline")
    if smoke_build.two_pass_extraction:
        cmd.append("--two-pass-extraction")
    if smoke_build.prefer_grounded_named_entities:
        cmd.append("--prefer-grounded-named-entities")
    if smoke_build.skip_entity_vdb:
        cmd.append("--skip-entity-vdb")
    if smoke_build.skip_relationship_vdb:
        cmd.append("--skip-relationship-vdb")
    return cmd


def expected_smoke_artifact_paths(
    *,
    repo_root: Path,
    smoke_build: SmokeBuildConfig,
) -> list[Path]:
    """Resolve required smoke-build artifact paths from the typed artifact contract."""

    artifact_root = (
        _repo_path(repo_root, smoke_build.working_dir)
        / smoke_build.artifact_dataset_name
    )
    return [artifact_root / relative_path for relative_path in smoke_build.required_artifacts]


def run_smoke_build_validation(
    *,
    repo_root: Path,
    config: ExtractionIterationConfig,
    session_dir: Path,
    label: str,
) -> SmokeBuildValidationResult:
    """Run the bounded live-build gate and verify its required artifacts exist."""

    smoke_build = config.smoke_build
    if smoke_build is None:
        raise RuntimeError("Cannot run smoke-build validation without smoke_build config.")

    log_path = session_dir / f"{label}_smoke_build.log"
    run_logged_command(
        cmd=build_smoke_build_command(repo_root=repo_root, config=config),
        cwd=repo_root,
        log_path=log_path,
        timeout_seconds=config.runtime.validation_timeout_seconds,
    )
    checked_artifact_paths = expected_smoke_artifact_paths(
        repo_root=repo_root,
        smoke_build=smoke_build,
    )
    missing_artifacts = [path for path in checked_artifact_paths if not path.exists()]
    if missing_artifacts:
        missing_text = ", ".join(str(path) for path in missing_artifacts)
        raise RuntimeError(
            "Smoke build completed without all required artifacts: "
            f"{missing_text}"
        )
    return SmokeBuildValidationResult(
        log_file=log_path,
        checked_artifact_paths=checked_artifact_paths,
    )


async def run_fix_agent(
    *,
    repo_root: Path,
    config: ExtractionIterationConfig,
    session_dir: Path,
    cycle_index: int,
    baseline_results_file: Path,
) -> str:
    """Invoke the coding agent against the active extraction-family context."""

    agent_model = resolve_supervisor_agent_model(config)
    prompt_template = _repo_path(repo_root, config.prompt_template)
    messages = render_prompt(
        prompt_template,
        family_name=config.family.name,
        cases_file=str(_repo_path(repo_root, config.family.cases_file)),
        prompt_family=config.family.prompt_family,
        target_variant=config.family.target_variant,
        production_model=config.family.production_model,
        baseline_results_file=str(baseline_results_file),
        repo_root=str(repo_root),
    )
    trace_id = f"digimon.extraction_supervisor.{config.family.name}.{cycle_index:04d}"
    result = await acall_llm(
        agent_model,
        messages,
        task=config.agent.selection_task,
        trace_id=trace_id,
        max_budget=config.agent.max_budget,
        working_directory=str(repo_root),
        yolo_mode=config.agent.yolo_mode,
        max_turns=config.agent.max_turns,
        reasoning_effort=config.agent.reasoning_effort,
    )
    response_path = session_dir / f"cycle_{cycle_index:04d}_agent_response.txt"
    response_path.write_text(result.content, encoding="utf-8")
    return result.content


def commit_verified_improvement(
    *,
    repo_root: Path,
    family_name: str,
    target_variant: str,
    previous_snapshot: VariantScoreSnapshot,
    current_snapshot: VariantScoreSnapshot,
    validation_results_file: Path,
) -> str:
    """Create a detailed git commit for a verified extraction-family improvement."""

    changed_files = git_output(repo_root, "diff", "--name-only", "HEAD").splitlines()
    if not changed_files:
        raise RuntimeError("Refusing to commit a verified improvement with no code changes")

    subject = (
        "[Plan #7] "
        f"supervisor: improve {family_name} "
        f"({target_variant} "
        f"{previous_snapshot.promotion_mean_score:.3f}->"
        f"{current_snapshot.promotion_mean_score:.3f})"
    )
    body_lines = [
        "Verified extraction-family improvement:",
        f"- failure_family: {family_name}",
        f"- target_variant: {target_variant}",
        f"- promotion_basis: {current_snapshot.promotion_basis}",
        f"- promotion_dimension: {current_snapshot.promotion_dimension}",
        f"- previous_promotion_score: {previous_snapshot.promotion_mean_score:.6f}",
        f"- current_promotion_score: {current_snapshot.promotion_mean_score:.6f}",
        f"- previous_target_score: {previous_snapshot.target_mean_score}",
        f"- current_target_score: {current_snapshot.target_mean_score}",
        f"- previous_sentinel_score: {previous_snapshot.sentinel_mean_score}",
        f"- current_sentinel_score: {current_snapshot.sentinel_mean_score}",
        f"- validation_results_file: {validation_results_file}",
        "- changed_files:",
        *[f"  - {path}" for path in changed_files],
    ]
    subprocess.run(["git", "add", "-A"], cwd=str(repo_root), check=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", subject, "-m", "\n".join(body_lines)],
        cwd=str(repo_root),
        check=True,
    )
    return git_output(repo_root, "rev-parse", "HEAD")


def run_loop(
    config: ExtractionIterationConfig,
    *,
    session_id: str,
    max_cycles: int | None = None,
) -> Path:
    """Run the bounded extraction-family supervisor until time or cycle budget ends."""

    repo_root = Path(config.repo_root).resolve()
    validate_agent_runtime_dependencies(config)
    case_roles = load_family_case_role_index(
        _repo_path(repo_root, config.family.cases_file),
        failure_family=config.family.name,
    )
    results_root = _repo_path(repo_root, config.runtime.results_root)
    session_dir = results_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "state.json"
    ledger_path = session_dir / "ledger.jsonl"
    stop_flag = install_signal_stop_flag()

    if state_path.exists():
        state = read_state(state_path)
    else:
        state = LoopState(
            session_id=session_id,
            started_at=_utc_now().isoformat(),
        )
        write_state(state_path, state)

    deadline = _utc_now() + timedelta(hours=config.runtime.duration_hours)
    append_ledger_event(
        ledger_path,
        event_type="session_started",
        cycle=state.cycle_index,
        session_id=session_id,
        deadline=deadline.isoformat(),
        failure_family=config.family.name,
        target_case_count=len(case_roles.target_case_ids),
        sentinel_case_count=len(case_roles.sentinel_case_ids),
        smoke_build_enabled=config.smoke_build is not None,
    )

    while _utc_now() < deadline:
        if stop_flag["stop"]:
            append_ledger_event(
                ledger_path,
                event_type="session_stopped",
                cycle=state.cycle_index,
                reason="signal",
            )
            break
        if max_cycles is not None and state.cycle_index >= max_cycles:
            append_ledger_event(
                ledger_path,
                event_type="session_stopped",
                cycle=state.cycle_index,
                reason="max_cycles",
            )
            break
        if git_has_changes(repo_root):
            raise RuntimeError(
                "Extraction supervisor requires a clean worktree at cycle boundaries"
            )

        if state.baseline_results_file is None:
            baseline_results_file, baseline_log_file = run_prompt_eval_validation(
                repo_root=repo_root,
                config=config,
                session_dir=session_dir,
                label="baseline",
            )
            baseline_snapshot = extract_variant_score_snapshot(
                baseline_results_file,
                variant_name=config.family.target_variant,
                case_roles=case_roles,
                promotion_dimension=config.family.promotion_dimension,
            )
            state.baseline_results_file = str(baseline_results_file)
            state.baseline_log_file = str(baseline_log_file)
            write_state(state_path, state)
            append_ledger_event(
                ledger_path,
                event_type="baseline_recorded",
                cycle=state.cycle_index,
                results_file=str(baseline_results_file),
                log_file=str(baseline_log_file),
                **snapshot_ledger_fields(baseline_snapshot, prefix="baseline"),
            )

        baseline_results_file = Path(state.baseline_results_file)
        baseline_snapshot = extract_variant_score_snapshot(
            baseline_results_file,
            variant_name=config.family.target_variant,
            case_roles=case_roles,
            promotion_dimension=config.family.promotion_dimension,
        )

        state.cycle_index += 1
        write_state(state_path, state)
        append_ledger_event(
            ledger_path,
            event_type="cycle_started",
            cycle=state.cycle_index,
            failure_family=config.family.name,
            **snapshot_ledger_fields(baseline_snapshot, prefix="baseline"),
        )

        try:
            agent_response = asyncio.run(
                asyncio.wait_for(
                    run_fix_agent(
                        repo_root=repo_root,
                        config=config,
                        session_dir=session_dir,
                        cycle_index=state.cycle_index,
                        baseline_results_file=baseline_results_file,
                    ),
                    timeout=config.runtime.agent_timeout_seconds,
                )
            )
        except Exception as exc:
            if git_has_changes(repo_root):
                revert_worktree(repo_root)
            append_ledger_event(
                ledger_path,
                event_type="cycle_agent_error",
                cycle=state.cycle_index,
                **describe_exception(exc),
            )
            time.sleep(config.runtime.sleep_on_noop_seconds)
            continue

        append_ledger_event(
            ledger_path,
            event_type="agent_completed",
            cycle=state.cycle_index,
            changed=git_has_changes(repo_root),
            agent_response_chars=len(agent_response),
        )
        if not git_has_changes(repo_root):
            append_ledger_event(
                ledger_path,
                event_type="cycle_no_change",
                cycle=state.cycle_index,
            )
            time.sleep(config.runtime.sleep_on_noop_seconds)
            continue

        try:
            validation_results_file, validation_log_file = run_prompt_eval_validation(
                repo_root=repo_root,
                config=config,
                session_dir=session_dir,
                label=f"cycle_{state.cycle_index:04d}",
            )
            current_snapshot = extract_variant_score_snapshot(
                validation_results_file,
                variant_name=config.family.target_variant,
                case_roles=case_roles,
                promotion_dimension=config.family.promotion_dimension,
            )
        except Exception as exc:
            revert_worktree(repo_root)
            append_ledger_event(
                ledger_path,
                event_type="cycle_validation_error",
                cycle=state.cycle_index,
                **describe_exception(exc),
            )
            continue

        decision = evaluate_improvement(baseline_snapshot, current_snapshot)
        append_ledger_event(
            ledger_path,
            event_type="validation_completed",
            cycle=state.cycle_index,
            results_file=str(validation_results_file),
            log_file=str(validation_log_file),
            **snapshot_ledger_fields(baseline_snapshot, prefix="previous"),
            **snapshot_ledger_fields(current_snapshot, prefix="current"),
            **decision.model_dump(mode="json"),
        )

        if not decision.verified:
            revert_worktree(repo_root)
            append_ledger_event(
                ledger_path,
                event_type="cycle_reverted_gate_failure",
                cycle=state.cycle_index,
                **snapshot_ledger_fields(baseline_snapshot, prefix="previous"),
                **snapshot_ledger_fields(current_snapshot, prefix="current"),
                **decision.model_dump(mode="json"),
            )
            continue

        if config.smoke_build is not None:
            try:
                smoke_result = run_smoke_build_validation(
                    repo_root=repo_root,
                    config=config,
                    session_dir=session_dir,
                    label=f"cycle_{state.cycle_index:04d}",
                )
            except Exception as exc:
                revert_worktree(repo_root)
                append_ledger_event(
                    ledger_path,
                    event_type="cycle_smoke_build_error",
                    cycle=state.cycle_index,
                    **describe_exception(exc),
                )
                continue
            append_ledger_event(
                ledger_path,
                event_type="smoke_build_completed",
                cycle=state.cycle_index,
                log_file=str(smoke_result.log_file),
                checked_artifacts=[
                    str(path) for path in smoke_result.checked_artifact_paths
                ],
            )

        commit_hash = commit_verified_improvement(
            repo_root=repo_root,
            family_name=config.family.name,
            target_variant=config.family.target_variant,
            previous_snapshot=baseline_snapshot,
            current_snapshot=current_snapshot,
            validation_results_file=validation_results_file,
        )
        state.baseline_results_file = str(validation_results_file)
        state.baseline_log_file = str(validation_log_file)
        state.latest_commit = commit_hash
        write_state(state_path, state)
        append_ledger_event(
            ledger_path,
            event_type="verified_commit_created",
            cycle=state.cycle_index,
            commit_hash=commit_hash,
            results_file=str(validation_results_file),
        )
    return session_dir


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the extraction supervisor."""

    parser = argparse.ArgumentParser(
        description="Run the DIGIMON extraction-family improvement supervisor."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="YAML config file for the extraction supervisor.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional explicit session ID. Defaults to a fresh UTC timestamp.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional cycle cap for bounded smoke runs.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point for the extraction supervisor."""

    args = parse_args()
    config = load_config(args.config)
    session_id = args.session_id or f"extract-{config.family.name}-{_utc_stamp()}"
    session_dir = run_loop(config, session_id=session_id, max_cycles=args.max_cycles)
    print(f"session_dir={session_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
