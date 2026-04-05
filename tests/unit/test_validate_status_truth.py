"""Unit tests for status truth validation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_status_truth import validate_repo


def _write_repo_scaffold(tmp_path: Path) -> None:
    """Create a minimal DIGIMON-like repo scaffold for truth-validation tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "Core" / "MCP").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "results").mkdir()

    (tmp_path / "prompts" / "agent_benchmark_consolidated.yaml").write_text('version: "3.6"\n')
    (tmp_path / "Makefile").write_text(
        "PROJECT := Digimon_for_KG_application\n"
        "STAG_TURNS ?= 6\n"
        "bench-musique:  ## Run MuSiQue 19q diagnostic set (STAG_TURNS=6 default)\n"
    )
    (tmp_path / "Core" / "MCP" / "tool_consolidation.py").write_text(
        "class ConsolidatedTools:\n"
        "    async def entity_search(\n"
        "        self,\n"
        "        query: str,\n"
        "        method: str = 'semantic',\n"
        "        top_k: int = 5,\n"
        "    ) -> str:\n"
        "        return query\n"
    )


def _write_result_artifact(path: Path, *, passed: int, total: int) -> None:
    """Write a minimal benchmark result artifact with llm_em results."""
    results = []
    for index in range(total):
        results.append(
            {
                "id": f"q{index}",
                "gold": "A",
                "predicted": "A" if index < passed else "B",
                "llm_em": 1 if index < passed else 0,
                "em": 1 if index < passed else 0,
                "primary_failure_class": "none" if index < passed else "IEE",
            }
        )
    path.write_text(
        json.dumps(
            {
                "dataset": "MuSiQue",
                "model": "openrouter/openai/gpt-5.4-mini",
                "n_questions": total,
                "n_completed": total,
                "avg_llm_em_judged": (passed / total) * 100,
                "avg_em": (passed / total) * 100,
                "results": results,
            }
        )
    )


def test_validate_repo_passes_when_docs_match_live_truth(tmp_path: Path) -> None:
    """Status docs aligned with code and artifacts should validate cleanly."""
    _write_repo_scaffold(tmp_path)
    artifact = tmp_path / "results" / "MuSiQue_run.json"
    _write_result_artifact(artifact, passed=6, total=19)

    (tmp_path / "CURRENT_STATUS.md").write_text(
        "# Status\n\n"
        "Prompt v3.6 is active.\n"
        "Live default remains top_k=5.\n"
        "Run default remains STAG_TURNS=6.\n"
        "619265 now anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )
    (tmp_path / "docs" / "handoff_2026_04_03.md").write_text(
        "# Handoff\n\n"
        "Prompt v3.6 remains active.\n"
        "Plan #28 is active.\n"
        "619265 anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )

    facts, issues = validate_repo(tmp_path)

    assert facts.prompt_version == "3.6"
    assert facts.stag_turns_default == 6
    assert facts.entity_search_top_k_default == 5
    assert issues == []


def test_validate_repo_reports_stale_claims_and_bad_counts(tmp_path: Path) -> None:
    """The validator should catch stale diagnoses, stale versions, and bad result counts."""
    _write_repo_scaffold(tmp_path)
    artifact = tmp_path / "results" / "MuSiQue_run.json"
    _write_result_artifact(artifact, passed=6, total=19)

    (tmp_path / "CURRENT_STATUS.md").write_text(
        "# Status\n\n"
        "Prompt v3.6 is active.\n"
        "Live default remains top_k=5.\n"
        "Run default remains STAG_TURNS=6.\n"
        "619265 now anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (10/19 = 52.6%)\n"
    )
    (tmp_path / "docs" / "handoff_2026_04_03.md").write_text(
        "# Handoff\n\n"
        "Prompt version 3.5 is active.\n"
        "619265 (Batman Beyond, gold=12) is the key case.\n"
        "| 754156 | Laos |\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )

    _facts, issues = validate_repo(tmp_path)
    codes = {issue.code for issue in issues}
    messages = "\n".join(issue.message for issue in issues)

    assert "result_claim_mismatch" in codes
    assert "forbidden_stale_claim" in codes
    assert "missing_required_truth_claim" in codes
    assert "prompt version 3.5" in messages or "Prompt v3.6" in messages


def test_validate_repo_can_measure_artifacts_from_external_root(tmp_path: Path) -> None:
    """Worktrees should be able to validate docs against artifacts stored elsewhere."""
    repo_root = tmp_path / "worktree"
    artifact_root = tmp_path / "canonical"
    _write_repo_scaffold(repo_root)
    (artifact_root / "results").mkdir(parents=True)
    artifact = artifact_root / "results" / "MuSiQue_run.json"
    _write_result_artifact(artifact, passed=6, total=19)

    (repo_root / "CURRENT_STATUS.md").write_text(
        "# Status\n\n"
        "Prompt v3.6 is active.\n"
        "Live default remains top_k=5.\n"
        "Run default remains STAG_TURNS=6.\n"
        "619265 now anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )
    (repo_root / "docs" / "handoff_2026_04_03.md").write_text(
        "# Handoff\n\n"
        "Prompt v3.6 remains active.\n"
        "Plan #28 is active.\n"
        "619265 anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )

    _facts, issues = validate_repo(repo_root, artifact_root=artifact_root)

    assert issues == []


def test_validate_repo_auto_finds_canonical_artifacts_from_worktree_pointer(tmp_path: Path) -> None:
    """Worktree validation should auto-search the canonical checkout for historical artifacts."""
    canonical_root = tmp_path / "canonical"
    repo_root = tmp_path / "worktrees" / "plan-28"
    git_dir = canonical_root / ".git" / "worktrees" / "plan-28"

    _write_repo_scaffold(repo_root)
    (canonical_root / ".git").mkdir(parents=True)
    git_dir.mkdir(parents=True)
    (repo_root / ".git").write_text(f"gitdir: {git_dir}\n")
    (git_dir / "commondir").write_text("../..\n")

    (canonical_root / "results").mkdir(parents=True)
    artifact = canonical_root / "results" / "MuSiQue_run.json"
    _write_result_artifact(artifact, passed=6, total=19)

    (repo_root / "CURRENT_STATUS.md").write_text(
        "# Status\n\n"
        "Prompt v3.6 is active.\n"
        "Live default remains top_k=5.\n"
        "Run default remains STAG_TURNS=6.\n"
        "619265 now anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )
    (repo_root / "docs" / "handoff_2026_04_03.md").write_text(
        "# Handoff\n\n"
        "Prompt v3.6 remains active.\n"
        "Plan #28 is active.\n"
        "619265 anchors on Ray Donovan.\n"
        "754156 gold is The dynasty regrouped and defeated the Portuguese.\n"
        f"- Latest: `results/{artifact.name}` (6/19 = 31.6%)\n"
    )

    _facts, issues = validate_repo(repo_root)

    assert issues == []
