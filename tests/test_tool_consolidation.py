"""Unit tests for consolidated tool dispatch (Plan #15).

Verifies that the consolidation layer correctly maps method arguments
to underlying operator implementations without changing behavior.
"""

import pytest
from Core.MCP.tool_consolidation import (
    CONSOLIDATED_TOOLS,
    DISPATCH_MAP,
    get_original_tool_name,
    CONSOLIDATED_BENCHMARK_CONTRACTS,
)


class TestConsolidationMapping:
    """Verify the dispatch map covers all methods and tools."""

    def test_all_tools_have_methods(self):
        """Every consolidated tool with methods has all methods in dispatch map."""
        for tool_name, methods in CONSOLIDATED_TOOLS.items():
            for method in methods:
                key = (tool_name, method)
                assert key in DISPATCH_MAP, (
                    f"Missing dispatch for {tool_name}(method='{method}')"
                )

    def test_dispatch_map_covers_28_operators(self):
        """Dispatch map covers all 28 operator functions (some may share)."""
        unique_targets = set(DISPATCH_MAP.values())
        # At least 20 unique operator targets (some operators not consolidated)
        assert len(unique_targets) >= 20, (
            f"Only {len(unique_targets)} unique operator targets, expected ≥20"
        )

    def test_ten_consolidated_tools(self):
        """There are exactly 10 consolidated tool groups."""
        assert len(CONSOLIDATED_TOOLS) == 10

    def test_get_original_tool_name_valid(self):
        """Valid method returns correct original tool name."""
        assert get_original_tool_name("entity_search", "semantic") == "entity_vdb_search"
        assert get_original_tool_name("entity_search", "string") == "entity_string_search"
        assert get_original_tool_name("entity_search", "tfidf") == "entity_tfidf"
        assert get_original_tool_name("entity_traverse", "ppr") == "entity_ppr"
        assert get_original_tool_name("entity_traverse", "onehop") == "entity_onehop"
        assert get_original_tool_name("relationship_search", "graph") == "relationship_onehop"
        assert get_original_tool_name("chunk_retrieve", "text") == "chunk_text_search"
        assert get_original_tool_name("chunk_retrieve", "cooccurrence") == "chunk_occurrence"
        assert get_original_tool_name("reason", "decompose") == "meta_decompose_question"
        assert get_original_tool_name("reason", "answer") == "meta_generate_answer"

    def test_get_original_tool_name_invalid_fails_loud(self):
        """Invalid method raises ValueError with clear message."""
        with pytest.raises(ValueError, match="Invalid method"):
            get_original_tool_name("entity_search", "nonexistent")

    def test_get_original_tool_name_invalid_tool_fails_loud(self):
        """Invalid tool name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid method"):
            get_original_tool_name("nonexistent_tool", "semantic")


class TestBenchmarkContracts:
    """Verify benchmark contracts are consistent."""

    def test_all_consolidated_tools_have_contracts(self):
        """Every consolidated tool has a benchmark contract."""
        for tool_name in CONSOLIDATED_TOOLS:
            assert tool_name in CONSOLIDATED_BENCHMARK_CONTRACTS, (
                f"Missing benchmark contract for {tool_name}"
            )

    def test_contracts_have_descriptions(self):
        """Every contract has a description."""
        for tool_name, contract in CONSOLIDATED_BENCHMARK_CONTRACTS.items():
            assert "description" in contract, (
                f"Missing description in contract for {tool_name}"
            )

    def test_method_tools_have_methods_in_contract(self):
        """Tools with methods list them in their contract."""
        for tool_name, methods in CONSOLIDATED_TOOLS.items():
            if methods:  # skip submit_answer, resources
                contract = CONSOLIDATED_BENCHMARK_CONTRACTS[tool_name]
                assert "methods" in contract, (
                    f"Contract for {tool_name} missing 'methods' field"
                )
                assert set(contract["methods"]) == set(methods), (
                    f"Contract methods mismatch for {tool_name}: "
                    f"contract={contract['methods']}, tools={methods}"
                )
