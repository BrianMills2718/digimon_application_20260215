#!/usr/bin/env python3
"""Validate DIGIMON status docs against live code defaults and result artifacts.

This validator is intentionally repo-specific. The goal is to keep
`CURRENT_STATUS.md` and the active handoff grounded in the actual maintained
benchmark lane instead of a stale narrative.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MeasuredFacts:
    """Live values measured from code and benchmark artifacts."""

    prompt_version: str
    stag_turns_default: int
    entity_search_top_k_default: int


@dataclass(frozen=True)
class TruthIssue:
    """A single contradiction or stale-claim finding."""

    code: str
    severity: str
    message: str
    evidence: dict[str, Any]


def _read_text(path: Path) -> str:
    """Read a file and fail loudly when it is missing."""
    return path.read_text()


def _extract_prompt_version(repo_root: Path) -> str:
    """Measure the active prompt version from the benchmark prompt file."""
    text = _read_text(repo_root / "prompts" / "agent_benchmark_consolidated.yaml")
    match = re.search(r'^version:\s*"(?P<value>[^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise ValueError("Could not find prompt version in prompts/agent_benchmark_consolidated.yaml")
    return match.group("value")


def _extract_stag_turns_default(repo_root: Path) -> int:
    """Measure the Makefile default for retrieval stagnation turns."""
    text = _read_text(repo_root / "Makefile")
    match = re.search(r"^STAG_TURNS \?= (?P<value>\d+)$", text, flags=re.MULTILINE)
    if not match:
        raise ValueError("Could not find STAG_TURNS default in Makefile")
    return int(match.group("value"))


def _extract_entity_search_top_k_default(repo_root: Path) -> int:
    """Measure the consolidated entity-search default from live code."""
    text = _read_text(repo_root / "Core" / "MCP" / "tool_consolidation.py")
    match = re.search(
        r"async def entity_search\(\s*.*?top_k: int = (?P<value>\d+),",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find entity_search top_k default in Core/MCP/tool_consolidation.py")
    return int(match.group("value"))


def measure_live_facts(repo_root: Path) -> MeasuredFacts:
    """Collect live benchmark-lane defaults from the maintained code path."""
    return MeasuredFacts(
        prompt_version=_extract_prompt_version(repo_root),
        stag_turns_default=_extract_stag_turns_default(repo_root),
        entity_search_top_k_default=_extract_entity_search_top_k_default(repo_root),
    )


def _load_artifact(path: Path) -> dict[str, Any]:
    """Load a benchmark result artifact and validate the top-level shape."""
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _artifact_llm_counts(payload: dict[str, Any]) -> tuple[int, int, float]:
    """Return passed, total, and percent from a benchmark artifact."""
    results = payload.get("results")
    if isinstance(results, list) and results:
        total = len(results)
        passed = sum(1 for item in results if float(item.get("llm_em", 0) or 0) > 0)
        percent = round((passed / total) * 100, 1)
        return passed, total, percent

    total = int(payload.get("n_llm_judged") or payload.get("n_questions") or 0)
    percent = round(float(payload.get("avg_llm_em_judged", 0) or 0), 1)
    passed = round((percent / 100) * total)
    return passed, total, percent


def _scan_result_reference_lines(
    *,
    repo_root: Path,
    artifact_root: Path,
    doc_path: Path,
) -> list[TruthIssue]:
    """Validate markdown result-file references and claimed 6/19-style counts."""
    issues: list[TruthIssue] = []
    for line_number, line in enumerate(_read_text(doc_path).splitlines(), start=1):
        path_match = re.search(r"results/[A-Za-z0-9._/-]+\.json(?![A-Za-z0-9])", line)
        if not path_match:
            continue
        relative_path = path_match.group(0)
        if "XXXX" in relative_path:
            continue
        artifact_path = artifact_root / relative_path
        if not artifact_path.exists():
            issues.append(
                TruthIssue(
                    code="missing_result_artifact",
                    severity="fail",
                    message=f"{doc_path.relative_to(repo_root)} references missing artifact {relative_path}",
                    evidence={"doc": str(doc_path.relative_to(repo_root)), "line": line_number, "artifact": relative_path},
                )
            )
            continue

        counts_match = re.search(
            r"(?P<passed>\d+)/(?P<total>\d+)\s*=\s*(?P<percent>\d+(?:\.\d+)?)%",
            line,
        )
        if not counts_match:
            continue

        payload = _load_artifact(artifact_path)
        actual_passed, actual_total, actual_percent = _artifact_llm_counts(payload)
        claimed_passed = int(counts_match.group("passed"))
        claimed_total = int(counts_match.group("total"))
        claimed_percent = round(float(counts_match.group("percent")), 1)

        if (claimed_passed, claimed_total, claimed_percent) != (
            actual_passed,
            actual_total,
            actual_percent,
        ):
            issues.append(
                TruthIssue(
                    code="result_claim_mismatch",
                    severity="fail",
                    message=(
                        f"{doc_path.relative_to(repo_root)} claims {claimed_passed}/{claimed_total} = "
                        f"{claimed_percent:.1f}% for {relative_path}, but the artifact measures "
                        f"{actual_passed}/{actual_total} = {actual_percent:.1f}%."
                    ),
                    evidence={
                        "doc": str(doc_path.relative_to(repo_root)),
                        "line": line_number,
                        "artifact": relative_path,
                        "claimed": {
                            "passed": claimed_passed,
                            "total": claimed_total,
                            "percent": claimed_percent,
                        },
                        "actual": {
                            "passed": actual_passed,
                            "total": actual_total,
                            "percent": actual_percent,
                        },
                    },
                )
            )
    return issues


def _require_any_pattern(
    *,
    issues: list[TruthIssue],
    repo_root: Path,
    doc_path: Path,
    patterns: list[str],
    label: str,
) -> None:
    """Require that at least one regex pattern is present in a document."""
    text = _read_text(doc_path)
    if any(re.search(pattern, text, flags=re.MULTILINE) for pattern in patterns):
        return
    issues.append(
        TruthIssue(
            code="missing_required_truth_claim",
            severity="fail",
            message=f"{doc_path.relative_to(repo_root)} is missing required truth claim: {label}",
            evidence={"doc": str(doc_path.relative_to(repo_root)), "label": label, "patterns": patterns},
        )
    )


def _forbid_pattern(
    *,
    issues: list[TruthIssue],
    repo_root: Path,
    doc_path: Path,
    pattern: str,
    label: str,
) -> None:
    """Fail when a stale or contradicted pattern is still present."""
    text = _read_text(doc_path)
    if not re.search(pattern, text, flags=re.MULTILINE):
        return
    issues.append(
        TruthIssue(
            code="forbidden_stale_claim",
            severity="fail",
            message=f"{doc_path.relative_to(repo_root)} still contains forbidden stale claim: {label}",
            evidence={"doc": str(doc_path.relative_to(repo_root)), "label": label, "pattern": pattern},
        )
    )


def validate_docs(
    repo_root: Path,
    artifact_root: Path,
    facts: MeasuredFacts,
    doc_paths: list[Path],
) -> list[TruthIssue]:
    """Validate the status docs against live defaults and known stale-claim traps."""
    issues: list[TruthIssue] = []

    for doc_path in doc_paths:
        issues.extend(
            _scan_result_reference_lines(
                repo_root=repo_root,
                artifact_root=artifact_root,
                doc_path=doc_path,
            )
        )

    current_status = repo_root / "CURRENT_STATUS.md"
    handoff = repo_root / "docs" / "handoff_2026_04_03.md"

    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        patterns=[rf"version {re.escape(facts.prompt_version)}", rf"Prompt v{re.escape(facts.prompt_version)}"],
        label=f"active prompt version {facts.prompt_version}",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        patterns=[rf"STAG_TURNS={facts.stag_turns_default}"],
        label=f"STAG_TURNS default {facts.stag_turns_default}",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        patterns=[rf"top_k={facts.entity_search_top_k_default}"],
        label=f"entity_search top_k default {facts.entity_search_top_k_default}",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        patterns=[r"Ray Donovan"],
        label="619265 corrected anchor family",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        patterns=[r"The dynasty regrouped and defeated the Portuguese"],
        label="754156 corrected gold answer",
    )
    _forbid_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        pattern=r"\|\s*754156\s*\|\s*Laos\s*\|",
        label="754156 gold answer listed as Laos",
    )
    _forbid_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=current_status,
        pattern=r"619265 \(Batman Beyond",
        label="619265 described as Batman Beyond case",
    )

    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        patterns=[r"Ray Donovan"],
        label="handoff carries 619265 correction",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        patterns=[r"The dynasty regrouped and defeated the Portuguese"],
        label="handoff carries 754156 correction",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        patterns=[rf"Prompt v{re.escape(facts.prompt_version)}", rf"version {re.escape(facts.prompt_version)}"],
        label=f"handoff prompt version {facts.prompt_version}",
    )
    _require_any_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        patterns=[r"Plan #28"],
        label="handoff references active truth-repair plan",
    )
    _forbid_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        pattern=r"\|\s*754156\s*\|\s*Laos\s*\|",
        label="handoff still lists Laos as the gold answer for 754156",
    )
    _forbid_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        pattern=r"619265 \(Batman Beyond",
        label="handoff still describes 619265 as Batman Beyond",
    )
    _forbid_pattern(
        issues=issues,
        repo_root=repo_root,
        doc_path=handoff,
        pattern=r"version 3\.5",
        label="handoff still claims prompt version 3.5",
    )

    return issues


def validate_repo(repo_root: Path, artifact_root: Path | None = None) -> tuple[MeasuredFacts, list[TruthIssue]]:
    """Measure live facts and validate the main DIGIMON truth surfaces."""
    repo_root = repo_root.resolve()
    artifact_root = (artifact_root or repo_root).resolve()
    facts = measure_live_facts(repo_root)
    doc_paths = [
        repo_root / "CURRENT_STATUS.md",
        repo_root / "docs" / "handoff_2026_04_03.md",
    ]
    issues = validate_docs(repo_root, artifact_root, facts, doc_paths)
    issues.sort(key=lambda item: (item.severity, item.code, item.message))
    return facts, issues


def _render_text(facts: MeasuredFacts, issues: list[TruthIssue]) -> str:
    """Render a compact text summary for terminal use."""
    lines = [
        "DIGIMON Truth Check",
        f"- Prompt version: {facts.prompt_version}",
        f"- STAG_TURNS default: {facts.stag_turns_default}",
        f"- entity_search top_k default: {facts.entity_search_top_k_default}",
        f"- Issues: {len(issues)}",
    ]
    if not issues:
        lines.append("- Overall: clean")
        return "\n".join(lines) + "\n"

    lines.append("- Findings:")
    for issue in issues:
        lines.append(f"  - [{issue.severity.upper()}] {issue.code}: {issue.message}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root to validate")
    parser.add_argument(
        "--artifact-root",
        help="Optional alternate root used to resolve results/... artifact references",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root) if args.artifact_root else None
    facts, issues = validate_repo(Path(args.repo_root), artifact_root=artifact_root)
    if args.json:
        print(
            json.dumps(
                {
                    "facts": asdict(facts),
                    "issues": [asdict(issue) for issue in issues],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(_render_text(facts, issues), end="")

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
