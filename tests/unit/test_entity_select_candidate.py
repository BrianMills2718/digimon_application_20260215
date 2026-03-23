"""Unit tests for benchmark-time canonical entity selection."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


def _load_server_module():
    """Import the MCP server module with a minimal FastMCP stub."""

    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    faiss_module = types.ModuleType("faiss")
    llama_vector_stores_module = types.ModuleType("llama_index.vector_stores")
    llama_vector_stores_faiss_module = types.ModuleType("llama_index.vector_stores.faiss")

    class FastMCP:
        """Minimal stub that preserves tool decorators during import."""

        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def tool(self):
            """Return a decorator that leaves tool functions unchanged."""

            def decorator(fn):
                return fn

            return decorator

    class FaissVectorStore:
        """Minimal stub for optional llama-index FAISS integration."""

        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    fastmcp_module.FastMCP = FastMCP
    llama_vector_stores_faiss_module.FaissVectorStore = FaissVectorStore
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = server_module
    sys.modules["mcp.server.fastmcp"] = fastmcp_module
    sys.modules["faiss"] = faiss_module
    sys.modules["llama_index.vector_stores"] = llama_vector_stores_module
    sys.modules["llama_index.vector_stores.faiss"] = llama_vector_stores_faiss_module

    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / "digimon_mcp_stdio_server.py"
    spec = importlib.util.spec_from_file_location("digimon_mcp_stdio_server_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def server_module(monkeypatch):
    """Import the server module and stub runtime initialization."""

    module = _load_server_module()

    async def _noop() -> None:
        return None

    monkeypatch.setattr(module, "_ensure_initialized", _noop)
    module._state = {"context": None}
    return module


def test_entity_select_candidate_requires_disambiguation_for_close_anchor_candidates(server_module) -> None:
    """Ambiguity-safe mode should refuse close plausible anchor candidates."""

    payload = asyncio.run(
        server_module.entity_select_candidate(
            candidate_entities=[
                {"entity_id": "joseph victor vanderbilt", "entity_name": "Joseph Victor Vanderbilt", "coarse_type": "person", "candidate_score": 0.93},
                {"entity_id": "gunnar asplund", "entity_name": "Gunnar Asplund", "coarse_type": "person", "candidate_score": 0.926},
                {"entity_id": "regional library system", "entity_name": "Regional Library System", "coarse_type": "organization", "candidate_score": 1.02},
            ],
            task_text="Who designed the Southeast Library?",
            require_unambiguous=True,
            ambiguity_score_gap=0.01,
            top_k=2,
        )
    )
    result = json.loads(payload)

    assert result["status"] == "needs_revision"
    assert result["n_selected"] == 0
    assert result["expected_coarse_types_source"] == "inferred"
    assert [item["entity_id"] for item in result["top_candidates"][:2]] == [
        "joseph victor vanderbilt",
        "gunnar asplund",
    ]


def test_entity_select_candidate_allows_clear_anchor_winner(server_module) -> None:
    """Ambiguity-safe mode should still return a winner when the gap is clear."""

    payload = asyncio.run(
        server_module.entity_select_candidate(
            candidate_entities=[
                {"entity_id": "joseph victor vanderbilt", "entity_name": "Joseph Victor Vanderbilt", "coarse_type": "person", "candidate_score": 0.93},
                {"entity_id": "gunnar asplund", "entity_name": "Gunnar Asplund", "coarse_type": "person", "candidate_score": 0.62},
                {"entity_id": "regional library system", "entity_name": "Regional Library System", "coarse_type": "organization", "candidate_score": 1.02},
            ],
            task_text="Who designed the Southeast Library?",
            require_unambiguous=True,
            ambiguity_score_gap=0.01,
            top_k=2,
        )
    )
    result = json.loads(payload)

    assert result["status"] == "ok"
    assert result["n_selected"] == 2
    assert result["selected_entities"][0]["entity_id"] == "joseph victor vanderbilt"
