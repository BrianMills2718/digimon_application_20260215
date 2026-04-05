#!/usr/bin/env python3
"""Resolve repo-local runtime paths for DIGIMON automation.

This module keeps worktree artifact lookup and DIGIMON runtime interpreter
selection truthful without depending on brittle shell-specific `conda run`
behavior.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    """Return paths in first-seen order with resolved duplicates removed."""
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _read_gitdir_pointer(repo_root: Path) -> Path | None:
    """Read `.git` when it is a linked-worktree pointer file."""
    git_entry = repo_root / ".git"
    if git_entry.is_dir():
        return git_entry.resolve()
    if not git_entry.is_file():
        return None
    lines = git_entry.read_text().splitlines()
    if not lines:
        return None
    first_line = lines[0].strip()
    if not first_line.startswith("gitdir:"):
        return None
    raw_target = first_line.split(":", 1)[1].strip()
    target = Path(raw_target).expanduser()
    if not target.is_absolute():
        target = (repo_root / target).resolve()
    return target


def infer_git_common_dir(repo_root: Path) -> Path | None:
    """Infer the shared git common-dir for normal repos and linked worktrees."""
    git_dir = _read_gitdir_pointer(repo_root.resolve())
    if git_dir is None:
        return None
    commondir_file = git_dir / "commondir"
    if commondir_file.is_file():
        common_dir = Path(commondir_file.read_text().strip()).expanduser()
        if not common_dir.is_absolute():
            common_dir = (git_dir / common_dir).resolve()
        return common_dir
    return git_dir


def infer_canonical_repo_root(repo_root: Path) -> Path:
    """Resolve the canonical checkout root backing the current repo/worktree."""
    repo_root = repo_root.resolve()
    common_dir = infer_git_common_dir(repo_root)
    if common_dir is None or common_dir.name != ".git":
        return repo_root
    return common_dir.parent.resolve()


def artifact_reference_roots(repo_root: Path, explicit_root: Path | None = None) -> list[Path]:
    """Return roots to search when docs reference `results/...` artifacts."""
    repo_root = repo_root.resolve()
    canonical_root = infer_canonical_repo_root(repo_root)
    ordered: list[Path] = []
    if explicit_root is not None:
        ordered.append(explicit_root)
    ordered.extend([repo_root, canonical_root])
    return _dedupe_paths(ordered)


def benchmark_glob_roots(repo_root: Path, explicit_root: Path | None = None) -> list[Path]:
    """Return roots to scan for benchmark-report glob expansion."""
    repo_root = repo_root.resolve()
    if explicit_root is not None:
        return _dedupe_paths([explicit_root])
    canonical_root = infer_canonical_repo_root(repo_root)
    return _dedupe_paths([repo_root, canonical_root])


def resolve_artifact_reference(relative_path: str | Path, roots: Iterable[Path]) -> Path | None:
    """Resolve a relative `results/...` reference against ordered artifact roots."""
    relative = Path(relative_path)
    for root in roots:
        candidate = root / relative
        if candidate.exists():
            return candidate.resolve()
    return None


def _candidate_env_python(prefix: Path) -> Path:
    """Return the Python executable path expected inside a virtual-env prefix."""
    if os.name == "nt":
        return prefix / "Scripts" / "python.exe"
    return prefix / "bin" / "python"


def _candidate_conda_roots() -> list[Path]:
    """Infer likely Conda installation roots from the live shell environment."""
    candidates: list[Path] = []
    for raw in (os.environ.get("CONDA_EXE"), shutil.which("conda")):
        if not raw:
            continue
        conda_path = Path(raw).expanduser().resolve()
        parent = conda_path.parent
        if parent.name in {"bin", "condabin", "Scripts"}:
            candidates.append(parent.parent)
        else:
            candidates.append(parent)
    home = Path.home()
    for directory_name in ("miniconda3", "miniforge3", "mambaforge", "anaconda3"):
        candidates.append(home / directory_name)
    return _dedupe_paths(candidates)


def resolve_digimon_python(env_name: str = "digimon") -> Path:
    """Resolve the Python interpreter for the DIGIMON runtime environment."""
    explicit = os.environ.get("DIGIMON_PYTHON", "").strip()
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if candidate.exists():
            return candidate
        raise FileNotFoundError(
            f"DIGIMON_PYTHON points to a missing interpreter: {candidate}"
        )

    current_prefix = Path(sys.prefix).expanduser().resolve()
    if current_prefix.name == env_name:
        current_python = Path(sys.executable).expanduser().resolve()
        if current_python.exists():
            return current_python

    conda_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        prefix_path = Path(conda_prefix).expanduser().resolve()
        if prefix_path.name == env_name:
            candidate = _candidate_env_python(prefix_path)
            if candidate.exists():
                return candidate

    for base_prefix in _candidate_conda_roots():
        candidate = _candidate_env_python(base_prefix / "envs" / env_name)
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Could not resolve the DIGIMON runtime interpreter. "
        "Set DIGIMON_PYTHON=/path/to/python explicitly."
    )
