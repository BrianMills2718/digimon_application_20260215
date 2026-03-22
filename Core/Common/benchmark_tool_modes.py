"""Shared benchmark-mode tool subsets for agent-benchmark surfaces.

These whitelists define intentional tool-surface reductions used by benchmark
profiles such as ``baseline`` and ``fixed_graph``. Keeping them in one module
prevents the direct Python backend and MCP stdio backend from drifting.
"""

from __future__ import annotations

from typing import Iterable

_MODE_TOOL_WHITELISTS: dict[str, frozenset[str]] = {
    "baseline": frozenset(
        {
            "chunk_text_search",
            "chunk_vdb_search",
            "submit_answer",
            "list_available_resources",
        }
    ),
    "fixed_graph": frozenset(
        {
            "entity_string_search",
            "entity_neighborhood",
            "entity_profile",
            "chunk_text_search",
            "chunk_get_text_by_chunk_ids",
            "list_available_resources",
            "submit_answer",
        }
    ),
}


def filter_tool_names_for_benchmark_mode(
    tool_names: Iterable[str],
    mode_name: str,
) -> list[str]:
    """Return the tool subset for a benchmark mode, or the original surface.

    Modes without an explicit whitelist keep the incoming tool surface
    unchanged. This lets ``hybrid`` and other unrestricted modes continue to
    use the full benchmark-eligible tool set.
    """

    normalized_mode = (mode_name or "").strip().lower()
    allowed = _MODE_TOOL_WHITELISTS.get(normalized_mode)
    if allowed is None:
        return list(tool_names)
    return [tool_name for tool_name in tool_names if tool_name in allowed]
