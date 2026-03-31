"""Unit tests for the MCP entity string-search tool."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types

import networkx as nx
import pytest


def _load_server_module():
    """Import the MCP server module with a minimal FastMCP stub."""

    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

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

    fastmcp_module.FastMCP = FastMCP
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = server_module
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / "digimon_mcp_stdio_server.py"
    spec = importlib.util.spec_from_file_location("digimon_mcp_stdio_server_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeNodesView:
    """Minimal node-view object supporting iteration and item access."""

    def __init__(self, data: dict[str, dict[str, object]]) -> None:
        self._data = data

    def __call__(self) -> list[str]:
        """Return all node identifiers."""

        return list(self._data.keys())

    def __getitem__(self, node_id: str) -> dict[str, object]:
        """Return attributes for one node."""

        return self._data[node_id]


class _FakeGraph:
    """Minimal graph object exposing the subset used by entity search."""

    def __init__(self, nodes: dict[str, dict[str, object]]) -> None:
        self.nodes = _FakeNodesView(nodes)


class _FakeStorage:
    """Simple storage wrapper exposing the NetworkX graph attribute used by the tool."""

    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph
        self.graph = graph


class _FakeGraphInstance:
    """Simple graph instance wrapper matching the server's expectations."""

    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = _FakeStorage(graph)


class _FakeContext:
    """Minimal graph context needed by `_resolve_graph_reference_id` and search."""

    def __init__(self, graph_id: str, graph: _FakeGraph) -> None:
        self._graph_id = graph_id
        self._graph_instance = _FakeGraphInstance(graph)

    def list_graphs(self) -> list[str]:
        """Return the one registered graph identifier."""

        return [self._graph_id]

    def get_graph_instance(self, graph_id: str):
        """Return the stored graph instance for the requested graph ID."""

        if graph_id == self._graph_id:
            return self._graph_instance
        return None


@pytest.fixture()
def server_module(monkeypatch):
    """Import the server module and stub runtime initialization."""

    module = _load_server_module()

    async def _noop() -> None:
        return None

    monkeypatch.setattr(module, "_ensure_initialized", _noop)
    return module


def test_entity_string_search_filters_invalid_nodes(server_module) -> None:
    """Invalid blank and single-letter nodes should not surface in results."""

    graph = _FakeGraph(
        {
            "": {"entity_type": "", "description": ""},
            "s": {"entity_type": "organization", "description": "bad candidate"},
            "j": {"entity_type": "event", "description": "bad candidate"},
            "sous": {"entity_type": "geo", "description": "partial token candidate"},
            "sous les pieds des femmes": {
                "entity_type": "event",
                "description": "A 1997 French drama film.",
            },
        }
    )
    server_module._state = {"context": _FakeContext("MuSiQue_ERGraph", graph)}

    payload = asyncio.run(
        server_module.entity_string_search(query="Sous les pieds des femmes", dataset_name="MuSiQue")
    )
    results = json.loads(payload)["matches"]
    names = [item["entity_name"] for item in results]

    assert "" not in names
    assert "s" not in names
    assert "j" not in names
    assert names[0] == "sous les pieds des femmes"


def test_entity_string_search_prefers_exact_match_over_prefix_noise(server_module) -> None:
    """Full-title matches should rank ahead of shorter prefix nodes."""

    graph = _FakeGraph(
        {
            "sous": {"entity_type": "geo", "description": "prefix noise"},
            "sous les pieds": {"entity_type": "event", "description": "partial phrase"},
            "sous les pieds des femmes": {
                "entity_type": "event",
                "description": "A 1997 French drama film.",
            },
        }
    )
    server_module._state = {"context": _FakeContext("MuSiQue_ERGraph", graph)}

    payload = asyncio.run(
        server_module.entity_string_search(query="Sous les pieds des femmes", dataset_name="MuSiQue")
    )
    first_result = json.loads(payload)["matches"][0]

    assert first_result["entity_name"] == "sous les pieds des femmes"
    assert first_result["match_type"] == "exact"


def test_entity_string_search_matches_unicode_names_from_ascii_query(server_module) -> None:
    """ASCII queries should still match stored Unicode entity names."""

    graph = _FakeGraph(
        {
            "São José dos Campos": {
                "entity_type": "geo",
                "description": "A city in the state of São Paulo, Brazil.",
            },
            "São José dos Quatro Marcos": {
                "entity_type": "geo",
                "description": "A municipality in Mato Grosso, Brazil.",
            },
        }
    )
    server_module._state = {"context": _FakeContext("MuSiQue_ERGraph", graph)}

    payload = asyncio.run(
        server_module.entity_string_search(query="sao jose dos campos", dataset_name="MuSiQue")
    )
    first_result = json.loads(payload)["matches"][0]

    assert first_result["entity_name"] == "São José dos Campos"
    assert first_result["canonical_name"] == "São José dos Campos"


def test_entity_string_search_uses_canonical_metadata_when_node_id_is_lossy(server_module) -> None:
    """Search ranking should prefer stored canonical display names over lossy node IDs."""

    graph = _FakeGraph(
        {
            "s o jos dos campos": {
                "canonical_name": "São José dos Campos",
                "search_keys": "são josé dos campos<SEP>sao jose dos campos",
                "entity_type": "geo",
                "description": "A city in the state of São Paulo, Brazil.",
            },
            "sao jose dos quatros marcos": {
                "canonical_name": "São José dos Quatro Marcos",
                "search_keys": "são josé dos quatro marcos<SEP>sao jose dos quatro marcos",
                "entity_type": "geo",
                "description": "A municipality in Mato Grosso, Brazil.",
            },
        }
    )
    server_module._state = {"context": _FakeContext("MuSiQue_ERGraph", graph)}

    payload = asyncio.run(
        server_module.entity_string_search(query="sao jose dos campos", dataset_name="MuSiQue")
    )
    first_result = json.loads(payload)["matches"][0]

    assert first_result["entity_name"] == "s o jos dos campos"
    assert first_result["canonical_name"] == "São José dos Campos"


def test_entity_profile_resolves_canonical_name_via_lookup_metadata(server_module) -> None:
    """Entity profiles should resolve via search keys when direct node-ID lookup would fail."""

    graph = nx.Graph()
    graph.add_node(
        "s o jos dos campos",
        entity_name="s o jos dos campos",
        canonical_name="São José dos Campos",
        search_keys="são josé dos campos<SEP>sao jose dos campos",
        aliases="S Jose dos Campos",
        entity_type="geo",
        description="A city in the state of São Paulo, Brazil.",
        source_id="chunk_239",
    )
    server_module._state = {"context": _FakeContext("MuSiQue_ERGraph", graph)}

    payload = asyncio.run(
        server_module.entity_profile(entity_name="São José dos Campos", dataset_name="MuSiQue")
    )
    result = json.loads(payload)

    assert result["entity_id"] == "s o jos dos campos"
    assert result["canonical_name"] == "São José dos Campos"
    assert "S Jose dos Campos" in result["aliases"]
    assert result["lookup_refs"]["node_id"] == "s o jos dos campos"
    assert "sao jose dos campos" in result["lookup_refs"]["search_keys"]
