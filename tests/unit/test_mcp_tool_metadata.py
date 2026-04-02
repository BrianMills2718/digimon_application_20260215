"""Tests for MCP tool operational metadata and catalog exposure."""

from __future__ import annotations

import digimon_mcp_stdio_server as dms

from Core.MCP.tool_metadata import get_tool_operational_metadata


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
