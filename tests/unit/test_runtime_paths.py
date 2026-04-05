"""Unit tests for DIGIMON runtime path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.runtime_paths import (
    artifact_reference_roots,
    infer_canonical_repo_root,
    resolve_digimon_python,
)


def test_infer_canonical_repo_root_from_worktree_git_pointer(tmp_path: Path) -> None:
    """Linked worktrees should resolve back to the canonical checkout root."""
    canonical_root = tmp_path / "canonical"
    repo_root = tmp_path / "worktrees" / "plan-28"
    git_dir = canonical_root / ".git" / "worktrees" / "plan-28"

    repo_root.mkdir(parents=True)
    (canonical_root / ".git").mkdir(parents=True)
    git_dir.mkdir(parents=True)
    (repo_root / ".git").write_text(f"gitdir: {git_dir}\n")
    (git_dir / "commondir").write_text("../..\n")

    assert infer_canonical_repo_root(repo_root) == canonical_root.resolve()


def test_artifact_reference_roots_include_repo_then_canonical(tmp_path: Path) -> None:
    """Artifact lookup should search the live repo and then the canonical checkout."""
    canonical_root = tmp_path / "canonical"
    repo_root = tmp_path / "worktrees" / "plan-28"
    git_dir = canonical_root / ".git" / "worktrees" / "plan-28"

    repo_root.mkdir(parents=True)
    (canonical_root / ".git").mkdir(parents=True)
    git_dir.mkdir(parents=True)
    (repo_root / ".git").write_text(f"gitdir: {git_dir}\n")
    (git_dir / "commondir").write_text("../..\n")

    roots = artifact_reference_roots(repo_root)

    assert roots == [repo_root.resolve(), canonical_root.resolve()]


def test_resolve_digimon_python_prefers_explicit_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit DIGIMON_PYTHON should override auto-detection."""
    interpreter = tmp_path / "envs" / "digimon" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/usr/bin/env python3\n")

    monkeypatch.setenv("DIGIMON_PYTHON", str(interpreter))

    assert resolve_digimon_python() == interpreter.resolve()


def test_resolve_digimon_python_derives_env_from_conda_exe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime resolver should derive the env path from CONDA_EXE without `conda run`."""
    conda_exe = tmp_path / "miniconda3" / "bin" / "conda"
    digimon_python = tmp_path / "miniconda3" / "envs" / "digimon" / "bin" / "python"
    conda_exe.parent.mkdir(parents=True)
    digimon_python.parent.mkdir(parents=True)
    conda_exe.write_text("#!/usr/bin/env bash\n")
    digimon_python.write_text("#!/usr/bin/env python3\n")

    monkeypatch.delenv("DIGIMON_PYTHON", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.setenv("CONDA_EXE", str(conda_exe))

    assert resolve_digimon_python() == digimon_python.resolve()
