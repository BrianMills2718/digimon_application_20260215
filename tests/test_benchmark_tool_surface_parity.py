"""Integration proof that benchmark tool surfaces stay backend-aligned."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

DATASET_NAME = "MuSiQue"
BENCHMARK_MODES = ("hybrid", "baseline", "fixed_graph")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.requires_data
def test_real_musique_tool_surface_matches_between_direct_and_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real benchmark artifacts should yield the same tool surface on both backends.

    This test uses the persisted MuSiQue ER graph build and compares the direct
    Python backend with the MCP stdio startup logic for the three benchmark
    modes we actually use in evaluation. It is intentionally data-backed rather
    than mocked because backend drift is a wiring problem, not a pure function
    problem.
    """

    repo_root = Path(__file__).resolve().parents[1]
    artifact_dir = repo_root / "results" / DATASET_NAME / "er_graph"
    assert (artifact_dir / "graph_build_manifest.json").exists(), artifact_dir
    assert (artifact_dir / "nx_data.graphml").exists(), artifact_dir

    monkeypatch.setenv("DIGIMON_BENCHMARK_MODE", "1")
    monkeypatch.setenv("DIGIMON_PRELOAD_DATASET", DATASET_NAME)
    monkeypatch.setenv("DIGIMON_SKIP_VDB_PRELOAD", "1")
    monkeypatch.setenv("DIGIMON_LOG_LEVEL", "WARNING")

    import digimon_mcp_stdio_server as dms
    import eval.run_agent_benchmark as benchmark_runner

    async def _run_parity_check() -> None:
        for mode_name in BENCHMARK_MODES:
            monkeypatch.setenv("DIGIMON_BENCHMARK_MODE_NAME", mode_name)
            direct_tools = await benchmark_runner._init_direct_tools(
                DATASET_NAME,
                disable_embedding_tools=True,
            )
            direct_tool_names = sorted(tool.__name__ for tool in direct_tools)
            (
                mcp_tool_names,
                applicability_label,
                unavailable_tool_names,
                degraded_tool_names,
            ) = await dms._benchmark_visible_mcp_tool_names_for_current_env()

            assert sorted(mcp_tool_names) == direct_tool_names, (
                f"mode={mode_name} "
                f"applicability={applicability_label} "
                f"direct={direct_tool_names} "
                f"mcp={sorted(mcp_tool_names)} "
                f"unavailable={sorted(unavailable_tool_names)} "
                f"degraded={sorted(degraded_tool_names)}"
            )

    asyncio.run(_run_parity_check())
