"""Tests for MCP tool operational metadata and catalog exposure."""

from __future__ import annotations

import digimon_mcp_stdio_server as dms

from Core.MCP.tool_metadata import (
    get_missing_tool_metadata,
    get_tool_operational_metadata,
)


def test_operational_metadata_classifies_known_tools() -> None:
    """Known tools should map to the expected dummy metadata tiers."""
    catalog_meta = get_tool_operational_metadata("list_tool_catalog")
    assert catalog_meta.cost_tier == "low"
    assert catalog_meta.reliability_tier == "stable"

    answer_meta = get_tool_operational_metadata("meta_generate_answer")
    assert answer_meta.cost_tier == "high"
    assert answer_meta.reliability_tier == "experimental"


def test_collect_tool_catalog_includes_metadata_for_visible_tools() -> None:
    """The live MCP catalog should expose operational metadata fields."""
    tools = dms._collect_tool_catalog()
    entry = next(tool for tool in tools if tool["name"] == "list_tool_catalog")

    assert entry["visibility"] == "visible"
    assert entry["cost_tier"] == "low"
    assert entry["reliability_tier"] == "stable"
    assert "parameters" in entry
    assert entry["notes"]


def test_registered_fastmcp_tools_store_operational_metadata_on_meta() -> None:
    """Live FastMCP tool objects should carry the same operational metadata."""
    tool = dms.mcp._tool_manager._tools["entity_vdb_search"]

    assert isinstance(tool.meta, dict)
    assert tool.meta["cost_tier"] == "medium"
    assert tool.meta["reliability_tier"] == "beta"
    assert tool.meta["notes"]


def test_every_registered_fastmcp_tool_has_explicit_metadata() -> None:
    """The maintained digimon-kgrag tool surface should have no metadata gaps."""
    missing = get_missing_tool_metadata(dms.mcp._tool_manager._tools.keys())
    assert missing == []
