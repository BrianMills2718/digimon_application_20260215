"""Tests for progressive disclosure of MCP tools.

Verifies the always-loaded tool list, deferred tool registry, search function,
and should_defer_tool logic without requiring a running MCP server or LLM calls.
"""

from __future__ import annotations

import pytest

from Core.MCP.progressive_disclosure import (
    ALWAYS_LOADED_TOOLS,
    EXECUTE_CHAIN_TOOL_NAME,
    SEARCH_TOOL_NAME,
    DeferredToolRegistry,
    search_available_tools_impl,
    should_defer_tool,
)


# ---- Fixtures ----

@pytest.fixture
def populated_registry() -> DeferredToolRegistry:
    """Registry with a representative set of deferred tools for search tests."""
    registry = DeferredToolRegistry()
    registry.register(
        "entity_vdb_search",
        "Search for entities similar to a query using vector database similarity.",
        {"properties": {"query_text": {"type": "string"}, "top_k": {"type": "integer"}}},
    )
    registry.register(
        "entity_onehop",
        "Get all neighbor entities of a given entity in the graph.",
        {"properties": {"entity_ids": {"type": "array"}}},
    )
    registry.register(
        "entity_ppr",
        "Personalized PageRank from seed entities.",
        {"properties": {"seed_entity_ids": {"type": "array"}}},
    )
    registry.register(
        "entity_tfidf",
        "Find entities by TF-IDF keyword matching.",
        {"properties": {"query_text": {"type": "string"}}},
    )
    registry.register(
        "relationship_onehop",
        "Get typed relationships for an entity.",
        {"properties": {"entity_ids": {"type": "array"}}},
    )
    registry.register(
        "relationship_vdb_search",
        "Semantic vector search over relationships.",
        {"properties": {"query_text": {"type": "string"}}},
    )
    registry.register(
        "chunk_from_relationships",
        "Get text chunks for given relationships.",
        {"properties": {"target_relationships": {"type": "array"}}},
    )
    registry.register(
        "chunk_occurrence",
        "Find chunks where entities co-occur.",
        {"properties": {"entity_names": {"type": "array"}}},
    )
    registry.register(
        "chunk_vdb_search",
        "Semantic vector search over source text chunks.",
        {"properties": {"query_text": {"type": "string"}}},
    )
    registry.register(
        "chunk_text_search",
        "Keyword search over source text chunks.",
        {"properties": {"query_text": {"type": "string"}}},
    )
    registry.register(
        "meta_extract_entities",
        "Extract entity names from a text passage using LLM.",
        {"properties": {"query_text": {"type": "string"}}},
    )
    registry.register(
        "subgraph_steiner_tree",
        "Minimal subgraph connecting a set of entities.",
        {"properties": {"entity_ids": {"type": "array"}}},
    )
    return registry


# ---- Tests ----

class TestAlwaysLoadedTools:
    """Verify the always-loaded tool set."""

    def test_always_loaded_tools_list(self) -> None:
        """ALWAYS_LOADED_TOOLS contains the expected 5 tools."""
        expected = {
            "list_operators",
            "get_compatible_successors",
            "list_available_resources",
            "meta_generate_answer",
            "submit_answer",
        }
        assert set(ALWAYS_LOADED_TOOLS) == expected
        assert len(ALWAYS_LOADED_TOOLS) == 5


class TestShouldDeferTool:
    """Verify should_defer_tool classifies tools correctly."""

    def test_always_loaded_not_deferred(self) -> None:
        """Always-loaded tools return False (not deferred)."""
        for tool_name in ALWAYS_LOADED_TOOLS:
            assert not should_defer_tool(tool_name), f"{tool_name} should NOT be deferred"

    def test_search_tool_not_deferred(self) -> None:
        """The search tool itself is never deferred."""
        assert not should_defer_tool(SEARCH_TOOL_NAME)

    def test_execute_chain_not_deferred(self) -> None:
        """The execute_operator_chain tool is never deferred."""
        assert not should_defer_tool(EXECUTE_CHAIN_TOOL_NAME)

    def test_regular_tools_are_deferred(self) -> None:
        """Non-always-loaded tools return True (deferred)."""
        deferred_examples = [
            "entity_vdb_search",
            "entity_onehop",
            "relationship_onehop",
            "chunk_occurrence",
            "chunk_from_relationships",
            "graph_build_er",
            "corpus_prepare",
            "get_config",
        ]
        for tool_name in deferred_examples:
            assert should_defer_tool(tool_name), f"{tool_name} should be deferred"


class TestDeferredToolRegistry:
    """Verify registry CRUD operations."""

    def test_register_and_get(self) -> None:
        """Registered tools can be retrieved by name."""
        registry = DeferredToolRegistry()
        registry.register("my_tool", "Does something", {"param": "schema"})
        tool = registry.get("my_tool")
        assert tool is not None
        assert tool.name == "my_tool"
        assert tool.description == "Does something"
        assert tool.parameters == {"param": "schema"}

    def test_contains(self) -> None:
        """Containment check works."""
        registry = DeferredToolRegistry()
        registry.register("my_tool", "Does something")
        assert "my_tool" in registry
        assert "other_tool" not in registry

    def test_len(self) -> None:
        """Length reflects number of registered tools."""
        registry = DeferredToolRegistry()
        assert len(registry) == 0
        registry.register("a", "first")
        registry.register("b", "second")
        assert len(registry) == 2


class TestSearchAvailableTools:
    """Verify keyword search over deferred tools."""

    def test_search_finds_tool_by_name(self, populated_registry: DeferredToolRegistry) -> None:
        """Searching 'entity_vdb' should return entity_vdb_search."""
        results = search_available_tools_impl("entity_vdb", populated_registry)
        names = [r["name"] for r in results]
        assert "entity_vdb_search" in names

    def test_search_finds_tool_by_description(self, populated_registry: DeferredToolRegistry) -> None:
        """Searching 'vector database' should return VDB tools."""
        results = search_available_tools_impl("vector database", populated_registry)
        names = [r["name"] for r in results]
        # Should find tools with 'vector' and 'database' in description
        vdb_tools = [n for n in names if "vdb" in n]
        assert len(vdb_tools) > 0, f"Expected VDB tools in results, got {names}"

    def test_search_returns_max_results(self, populated_registry: DeferredToolRegistry) -> None:
        """Search for 'entity' with many matches returns at most top_k."""
        results = search_available_tools_impl("entity", populated_registry, top_k=3)
        assert len(results) <= 3

    def test_search_empty_query(self, populated_registry: DeferredToolRegistry) -> None:
        """Empty query returns empty results."""
        results = search_available_tools_impl("", populated_registry)
        assert results == []

    def test_search_no_matches(self, populated_registry: DeferredToolRegistry) -> None:
        """Query with no matching tokens returns empty results."""
        results = search_available_tools_impl("zzzznonexistent", populated_registry)
        assert results == []

    def test_search_result_structure(self, populated_registry: DeferredToolRegistry) -> None:
        """Each result has name, description, and parameters keys."""
        results = search_available_tools_impl("entity_vdb", populated_registry)
        assert len(results) > 0
        for r in results:
            assert "name" in r
            assert "description" in r
            assert "parameters" in r

    def test_search_prioritizes_name_match(self, populated_registry: DeferredToolRegistry) -> None:
        """Exact name substring match is ranked higher than description-only match."""
        results = search_available_tools_impl("chunk_vdb_search", populated_registry)
        assert len(results) > 0
        assert results[0]["name"] == "chunk_vdb_search"
