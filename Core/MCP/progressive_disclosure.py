"""Progressive disclosure for DIGIMON MCP tool surface.

Instead of exposing all 50+ tools at MCP init, progressive disclosure
keeps only a small always-loaded set visible. A search tool lets the
agent discover deferred tools by keyword, and the caller can register
them on demand.

Activated via DIGIMON_PROGRESSIVE_DISCLOSURE=1 env var.
Without it, all tools are registered as today (backward compatible).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from Core.MCP.tool_metadata import get_tool_operational_metadata


# ---- Always-loaded tools ----
# These 6 tools are always visible to the agent regardless of disclosure mode.
# They cover: discovery/catalog (3), context inspection (1), answer generation
# (1), and benchmark submission (1).
ALWAYS_LOADED_TOOLS: list[str] = [
    "list_tool_catalog",
    "list_operators",
    "get_compatible_successors",
    "list_available_resources",
    "meta_generate_answer",
    "submit_answer",
]

# The search tool itself is always loaded when progressive disclosure is active.
# It is not in ALWAYS_LOADED_TOOLS because it doesn't exist outside disclosure mode.
SEARCH_TOOL_NAME = "search_available_tools"

# execute_operator_chain is always loaded (available in all modes).
EXECUTE_CHAIN_TOOL_NAME = "execute_operator_chain"


@dataclass
class DeferredToolInfo:
    """Metadata for a deferred (hidden) tool, used by the search function."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    cost_tier: str = "medium"
    reliability_tier: str = "beta"
    notes: str = ""

    def to_result_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation for MCP search responses."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "cost_tier": self.cost_tier,
            "reliability_tier": self.reliability_tier,
            "notes": self.notes,
        }


class DeferredToolRegistry:
    """Registry of tools removed from the MCP surface for progressive disclosure.

    Stores tool metadata so the search function can return descriptions and
    parameter schemas without the tools being registered on the MCP server.
    """

    def __init__(self) -> None:
        """Initialize an empty deferred tool registry."""
        self._tools: dict[str, DeferredToolInfo] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        cost_tier: str | None = None,
        reliability_tier: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Add a deferred tool's metadata to the registry.

        Args:
            name: Tool function name (e.g. 'entity_vdb_search').
            description: Tool docstring or short description.
            parameters: JSON schema dict for the tool's parameters.
            cost_tier: Coarse relative cost hint for tool selection.
            reliability_tier: Coarse reliability hint for tool selection.
            notes: Free-text explanation of the operational metadata.
        """
        operational = get_tool_operational_metadata(name)
        self._tools[name] = DeferredToolInfo(
            name=name,
            description=description,
            parameters=parameters or {},
            cost_tier=cost_tier or operational.cost_tier,
            reliability_tier=reliability_tier or operational.reliability_tier,
            notes=notes or operational.notes,
        )

    def get(self, name: str) -> DeferredToolInfo | None:
        """Look up a deferred tool by exact name."""
        return self._tools.get(name)

    def all_tools(self) -> list[DeferredToolInfo]:
        """Return all deferred tools, sorted by name."""
        return sorted(self._tools.values(), key=lambda t: t.name)

    def __len__(self) -> int:
        """Number of deferred tools in the registry."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if a tool name is in the deferred registry."""
        return name in self._tools


def should_defer_tool(tool_name: str) -> bool:
    """Return True if a tool should be deferred (hidden) in progressive disclosure mode.

    Always-loaded tools, the search tool, and the execute_operator_chain tool
    are never deferred. Everything else is.

    Args:
        tool_name: The MCP tool function name.
    """
    if tool_name in ALWAYS_LOADED_TOOLS:
        return False
    if tool_name == SEARCH_TOOL_NAME:
        return False
    if tool_name == EXECUTE_CHAIN_TOOL_NAME:
        return False
    return True


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase alphanumeric tokens for keyword matching.

    Args:
        text: Input string to tokenize.

    Returns:
        Set of lowercase tokens.
    """
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def search_available_tools_impl(
    query: str,
    registry: DeferredToolRegistry,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search deferred tools by keyword match against name and description.

    Scores each tool by how many query tokens appear in its name + description.
    Returns the top_k highest-scoring tools.

    Args:
        query: Free-text search query from the agent.
        registry: The deferred tool registry to search.
        top_k: Maximum number of results to return.

    Returns:
        List of dicts with 'name', 'description', and 'parameters' keys,
        sorted by relevance (highest first).
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[float, DeferredToolInfo]] = []
    for tool in registry.all_tools():
        # Build searchable text from name (with underscores as separators) and description
        tool_text = tool.name.replace("_", " ") + " " + tool.description
        tool_tokens = _tokenize(tool_text)

        # Score = fraction of query tokens found in tool text
        matches = query_tokens & tool_tokens
        if not matches:
            continue
        score = len(matches) / len(query_tokens)

        # Bonus for exact substring match in name
        if query.lower().replace(" ", "_") in tool.name.lower():
            score += 1.0
        elif query.lower().replace("_", " ") in tool.name.lower().replace("_", " "):
            score += 0.5

        scored.append((score, tool))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        tool.to_result_dict()
        for _, tool in scored[:top_k]
    ]
