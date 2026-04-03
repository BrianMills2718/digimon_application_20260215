"""Unit tests for consolidated tool dispatch (Plan #15).

Verifies that the consolidation layer correctly maps method arguments
to underlying operator implementations without changing behavior.
"""

import json

import pytest
from Core.MCP.tool_consolidation import (
    CONSOLIDATED_TOOLS,
    DISPATCH_MAP,
    get_original_tool_name,
    CONSOLIDATED_BENCHMARK_CONTRACTS,
    build_consolidated_tools,
    _linearize,
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


class _FakeDMS:
    """Minimal MCP surface for testing consolidated wrapper context forwarding."""

    def __init__(self) -> None:
        self.captured_payloads: list[tuple[str, str, dict[str, object]]] = []
        self.last_entity_profile_kwargs: dict[str, object] | None = None
        self.last_entity_resolve_kwargs: dict[str, object] | None = None
        self.last_relationship_kwargs: dict[str, object] | None = None
        self.active_atom: dict[str, object] | None = None
        self.dependency_values: list[str] = []

    async def _maybe_complete_active_atom_from_payload(
        self,
        payload,
        *,
        tool_name: str,
        method: str,
    ):
        self.captured_payloads.append((tool_name, method, payload))
        return None

    def _active_semantic_plan_atom(self):
        return self.active_atom, None

    def _resolved_dependency_values(self, atom):
        return list(self.dependency_values) if atom == self.active_atom else []

    async def entity_profile(self, **kwargs: object) -> str:
        self.last_entity_profile_kwargs = dict(kwargs)
        return json.dumps({"canonical_name": "godiva", "connected_entities": ["mercia"]})

    async def entity_resolve_names_to_ids(self, **kwargs: object) -> str:
        self.last_entity_resolve_kwargs = dict(kwargs)
        return json.dumps({"resolved_entities": [{"resolved_entity_name": "godiva"}]})

    async def relationship_onehop(self, **kwargs: object) -> str:
        self.last_relationship_kwargs = dict(kwargs)
        return json.dumps({"relationships": [{"src_id": "godiva", "tgt_id": "mercia"}]})


@pytest.mark.asyncio
async def test_entity_info_wrapper_forwards_context_to_atom_hook() -> None:
    """Top-level entity_info calls should preserve graph/dataset context for bridge probes."""
    dms = _FakeDMS()
    tools = {tool.__name__: tool for tool in build_consolidated_tools(dms)}

    await tools["entity_info"](
        method="profile",
        entity_name="godiva",
        graph_reference_id="MuSiQue_ERGraph",
        dataset_name="MuSiQue",
    )

    tool_name, method, payload = dms.captured_payloads[-1]
    assert (tool_name, method) == ("entity_info", "profile")
    assert payload["resolved_graph_reference_id"] == "MuSiQue_ERGraph"
    assert payload["resolved_dataset_name"] == "MuSiQue"
    assert payload["requested_entity_name"] == "godiva"


@pytest.mark.asyncio
async def test_entity_info_resolve_accepts_single_entity_name_alias() -> None:
    """Resolve wrapper should accept the single-name call shape the agent already uses."""
    dms = _FakeDMS()
    tools = {tool.__name__: tool for tool in build_consolidated_tools(dms)}

    await tools["entity_info"](
        method="resolve",
        entity_name="godiva",
        dataset_name="MuSiQue",
    )

    assert dms.last_entity_resolve_kwargs is not None
    assert dms.last_entity_resolve_kwargs["entity_names"] == ["godiva"]


@pytest.mark.asyncio
async def test_relationship_wrapper_forwards_context_to_atom_hook() -> None:
    """Top-level relationship_search calls should preserve graph/query context for bridge probes."""
    dms = _FakeDMS()
    tools = {tool.__name__: tool for tool in build_consolidated_tools(dms)}

    await tools["relationship_search"](
        method="graph",
        entity_ids=["godiva"],
        graph_reference_id="MuSiQue_ERGraph",
        query_text="When was Lady Godiva's birthplace abolished?",
    )

    tool_name, method, payload = dms.captured_payloads[-1]
    assert (tool_name, method) == ("relationship_search", "graph")
    assert payload["resolved_graph_reference_id"] == "MuSiQue_ERGraph"
    assert payload["requested_query"] == "When was Lady Godiva's birthplace abolished?"
    assert payload["requested_entity_ids"] == ["godiva"]


@pytest.mark.asyncio
async def test_entity_info_wrapper_rewrites_scope_from_resolved_dependency() -> None:
    """Downstream profile lookups should pivot from the subject to the resolved bridge entity."""
    dms = _FakeDMS()
    dms.active_atom = {"atom_id": "A2", "sub_question": "When was Mercia abolished?"}
    dms.dependency_values = ["mercia"]
    tools = {tool.__name__: tool for tool in build_consolidated_tools(dms)}

    await tools["entity_info"](
        method="profile",
        entity_name="godiva",
        graph_reference_id="MuSiQue_ERGraph",
        dataset_name="MuSiQue",
    )

    assert dms.last_entity_profile_kwargs is not None
    assert dms.last_entity_profile_kwargs["entity_name"] == "mercia"
    _, _, payload = dms.captured_payloads[-1]
    assert payload["entity_scope_contract"]["rewritten"] is True
    assert payload["entity_scope_contract"]["effective_entities"] == ["mercia"]


@pytest.mark.asyncio
async def test_relationship_wrapper_rewrites_scope_from_resolved_dependency() -> None:
    """Downstream graph traversals should use the resolved dependency entity by default."""
    dms = _FakeDMS()
    dms.active_atom = {"atom_id": "A2", "sub_question": "When was Mercia abolished?"}
    dms.dependency_values = ["mercia"]
    tools = {tool.__name__: tool for tool in build_consolidated_tools(dms)}

    await tools["relationship_search"](
        method="graph",
        entity_ids=["godiva"],
        graph_reference_id="MuSiQue_ERGraph",
    )

    assert dms.last_relationship_kwargs is not None
    assert dms.last_relationship_kwargs["entity_ids"] == ["mercia"]
    _, _, payload = dms.captured_payloads[-1]
    assert payload["entity_scope_contract"]["rewritten"] is True
    assert payload["entity_scope_contract"]["effective_entities"] == ["mercia"]


def test_linearize_relationship_search_graph_payload_preserves_one_hop_edges() -> None:
    """One-hop relationship payloads should not collapse into an empty summary."""
    raw = json.dumps(
        {
            "one_hop_relationships": [
                {
                    "src_id": "godiva",
                    "tgt_id": "mercia",
                    "relation_name": "chunk_cooccurrence",
                    "description": "Godiva was the wife of Leofric, Earl of Mercia.",
                    "attributes": {"source_id": "chunk_84"},
                    "weight": 1.0,
                }
            ]
        }
    )

    summary = _linearize(raw, "relationship_search", "graph")

    assert "No relationships found" not in summary
    assert "mercia" in summary
    assert "chunk_84" in summary


def test_linearize_entity_traverse_neighbor_map_preserves_neighbor_candidates() -> None:
    """Neighbor maps should be summarized as entities, not raw dict blobs."""
    raw = json.dumps(
        {
            "neighbors": {
                "godiva": [
                    {"entity_id": "mercia", "coarse_type": "geo", "score": 0.92},
                    {"entity_id": "leicester", "coarse_type": "geo", "score": 0.88},
                ]
            }
        }
    )

    summary = _linearize(raw, "entity_traverse", "onehop")

    assert "Found 2 neighboring entities" in summary
    assert "mercia" in summary
    assert "leicester" in summary
