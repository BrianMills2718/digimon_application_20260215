"""Operational metadata for DIGIMON MCP tools.

The current values are intentionally coarse planning hints rather than measured
runtime telemetry. They let MCP clients reason about relative tool cost and
trustworthiness today, while leaving room to replace these dummy tiers with
observed metrics later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ToolOperationalMetadata:
    """Coarse cost and reliability metadata attached to an MCP tool."""

    cost_tier: str
    reliability_tier: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable metadata dictionary."""
        return asdict(self)


_LOW_STABLE = ToolOperationalMetadata(
    cost_tier="low",
    reliability_tier="stable",
    notes="Cheap deterministic lookup or control tool.",
)
_MEDIUM_STABLE = ToolOperationalMetadata(
    cost_tier="medium",
    reliability_tier="stable",
    notes="Graph or retrieval operation with predictable behavior.",
)
_MEDIUM_BETA = ToolOperationalMetadata(
    cost_tier="medium",
    reliability_tier="beta",
    notes="Useful default tool with dependency or ranking sensitivity.",
)
_HIGH_BETA = ToolOperationalMetadata(
    cost_tier="high",
    reliability_tier="beta",
    notes="Expensive multi-step operation; usable but not yet calibrated.",
)
_HIGH_EXPERIMENTAL = ToolOperationalMetadata(
    cost_tier="high",
    reliability_tier="experimental",
    notes="LLM-heavy or complex orchestration path with higher variance.",
)


def get_tool_operational_metadata(tool_name: str) -> ToolOperationalMetadata:
    """Infer operational metadata for a DIGIMON MCP tool.

    Args:
        tool_name: MCP tool function name as registered on the FastMCP server.

    Returns:
        Coarse operational metadata for planning and attribution.
    """
    if tool_name in {
        "list_tool_catalog",
        "search_available_tools",
        "list_available_resources",
        "list_operators",
        "get_compatible_successors",
        "list_graph_types",
        "list_modality_conversions",
        "get_config",
        "submit_answer",
    }:
        return _LOW_STABLE

    if tool_name in {
        "entity_onehop",
        "entity_string_search",
        "entity_neighborhood",
        "entity_link",
        "entity_resolve_names_to_ids",
        "entity_profile",
        "entity_tfidf",
        "relationship_onehop",
        "chunk_from_relationships",
        "chunk_occurrence",
        "chunk_get_text",
        "chunk_get_text_by_chunk_ids",
        "chunk_get_text_by_entity_ids",
        "extract_date_mentions",
        "chunk_text_search",
        "search_then_expand_onehop",
    }:
        return _MEDIUM_STABLE

    if tool_name in {
        "entity_vdb_search",
        "entity_ppr",
        "entity_select_candidate",
        "relationship_score_aggregator",
        "relationship_vdb_search",
        "chunk_vdb_search",
        "chunk_aggregator",
        "community_detect_from_entities",
        "community_get_layer",
        "subgraph_khop_paths",
        "subgraph_steiner_tree",
        "graph_analyze",
        "graph_visualize",
        "augment_chunk_cooccurrence",
        "augment_centrality",
        "augment_synonym_edges",
    }:
        return _MEDIUM_BETA

    if tool_name.startswith("graph_build"):
        return _HIGH_BETA

    if tool_name in {
        "entity_agent",
        "relationship_agent",
        "subgraph_agent_path",
        "set_agentic_model",
        "convert_modality",
        "validate_conversion",
        "select_analysis_mode",
        "meta_extract_entities",
        "meta_generate_answer",
        "meta_pcst_optimize",
        "meta_decompose_question",
        "meta_synthesize_answers",
        "semantic_plan",
        "bridge_disambiguate",
        "todo_write",
        "execute_operator_chain",
    }:
        return _HIGH_EXPERIMENTAL

    return _MEDIUM_BETA
