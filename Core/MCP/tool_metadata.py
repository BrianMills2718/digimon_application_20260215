"""Operational metadata for DIGIMON MCP tools.

The current values are intentionally coarse planning hints rather than measured
runtime telemetry. They let MCP clients reason about relative tool cost and
trustworthiness today, while leaving room to replace these dummy tiers with
observed metrics later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ToolOperationalMetadata:
    """Coarse cost and reliability metadata attached to an MCP tool."""

    cost_tier: str
    reliability_tier: str
    notes: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable metadata dictionary."""
        return asdict(self)


_DEFAULT_OPERATIONAL_METADATA = ToolOperationalMetadata(
    cost_tier="medium",
    reliability_tier="beta",
    notes="Default placeholder metadata for unclassified or custom tools.",
)
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

_TOOL_OPERATIONAL_METADATA: dict[str, ToolOperationalMetadata] = {}


def _register_tool_metadata(
    tool_names: set[str],
    metadata: ToolOperationalMetadata,
) -> None:
    """Register a metadata bucket for a concrete set of DIGIMON MCP tools."""
    duplicate_names = sorted(tool_names & _TOOL_OPERATIONAL_METADATA.keys())
    if duplicate_names:
        raise ValueError(
            f"Duplicate MCP tool metadata registration for: {duplicate_names}",
        )
    for tool_name in tool_names:
        _TOOL_OPERATIONAL_METADATA[tool_name] = metadata


_register_tool_metadata(
    {
        "get_compatible_successors",
        "get_config",
        "list_available_resources",
        "list_graph_types",
        "list_modality_conversions",
        "list_operators",
        "list_tool_catalog",
        "search_available_tools",
        "submit_answer",
    },
    _LOW_STABLE,
)
_register_tool_metadata(
    {
        "chunk_from_relationships",
        "chunk_get_text",
        "chunk_get_text_by_chunk_ids",
        "chunk_get_text_by_entity_ids",
        "chunk_occurrence",
        "chunk_text_search",
        "entity_link",
        "entity_neighborhood",
        "entity_onehop",
        "entity_profile",
        "entity_resolve_names_to_ids",
        "entity_string_search",
        "entity_tfidf",
        "extract_date_mentions",
        "relationship_onehop",
        "search_then_expand_onehop",
    },
    _MEDIUM_STABLE,
)
_register_tool_metadata(
    {
        "augment_centrality",
        "augment_chunk_cooccurrence",
        "augment_synonym_edges",
        "build_communities",
        "build_sparse_matrices",
        "chunk_aggregator",
        "chunk_vdb_build",
        "chunk_vdb_search",
        "community_detect_from_entities",
        "community_get_layer",
        "corpus_prepare",
        "entity_ppr",
        "entity_select_candidate",
        "entity_vdb_build",
        "entity_vdb_search",
        "graph_analyze",
        "graph_visualize",
        "relationship_score_aggregator",
        "relationship_vdb_build",
        "relationship_vdb_search",
        "subgraph_khop_paths",
        "subgraph_steiner_tree",
    },
    _MEDIUM_BETA,
)
_register_tool_metadata(
    {
        "graph_build_er",
        "graph_build_passage",
        "graph_build_rk",
        "graph_build_tree",
        "graph_build_tree_balanced",
    },
    _HIGH_BETA,
)
_register_tool_metadata(
    {
        "bridge_disambiguate",
        "convert_modality",
        "entity_agent",
        "execute_operator_chain",
        "meta_decompose_question",
        "meta_extract_entities",
        "meta_generate_answer",
        "meta_pcst_optimize",
        "meta_synthesize_answers",
        "relationship_agent",
        "select_analysis_mode",
        "semantic_plan",
        "set_agentic_model",
        "subgraph_agent_path",
        "todo_write",
        "validate_conversion",
    },
    _HIGH_EXPERIMENTAL,
)


def get_tool_operational_metadata(
    tool_name: str,
    *,
    require_explicit: bool = False,
) -> ToolOperationalMetadata:
    """Infer operational metadata for a DIGIMON MCP tool.

    Args:
        tool_name: MCP tool function name as registered on the FastMCP server.
        require_explicit: When True, raise if the tool is missing from the
            explicit DIGIMON metadata registry instead of returning defaults.

    Returns:
        Coarse operational metadata for planning and attribution.
    """
    operational = _TOOL_OPERATIONAL_METADATA.get(tool_name)
    if operational is not None:
        return operational
    if require_explicit:
        raise KeyError(
            f"No explicit operational metadata registered for MCP tool: {tool_name}",
        )
    return _DEFAULT_OPERATIONAL_METADATA


def get_missing_tool_metadata(tool_names: Iterable[str]) -> list[str]:
    """Return registered tool names missing explicit operational metadata."""
    return sorted(set(tool_names) - _TOOL_OPERATIONAL_METADATA.keys())


def validate_tool_metadata_coverage(tool_names: Iterable[str]) -> None:
    """Fail loud when a live DIGIMON MCP tool lacks explicit metadata."""
    missing = get_missing_tool_metadata(tool_names)
    if missing:
        raise ValueError(
            "DIGIMON MCP tools missing explicit cost/reliability metadata: "
            + ", ".join(missing),
        )


def attach_tool_metadata_to_registry(tools_by_name: Mapping[str, Any]) -> None:
    """Attach operational metadata onto live FastMCP tool objects.

    The FastMCP `Tool` model exposes a `meta` field. We populate that field so
    discovery paths can read the same metadata directly from the registered tool
    object instead of recomputing it from a side table.
    """
    validate_tool_metadata_coverage(tools_by_name.keys())
    for tool_name, tool_obj in tools_by_name.items():
        operational = get_tool_operational_metadata(
            tool_name,
            require_explicit=True,
        )
        existing_meta = getattr(tool_obj, "meta", None)
        if existing_meta is None:
            merged_meta: dict[str, Any] = {}
        elif isinstance(existing_meta, dict):
            merged_meta = dict(existing_meta)
        else:
            raise TypeError(
                f"Unsupported FastMCP tool meta for {tool_name}: {type(existing_meta)!r}",
            )
        merged_meta.update(operational.to_dict())
        tool_obj.meta = merged_meta
