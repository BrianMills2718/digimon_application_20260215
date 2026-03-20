"""Regression tests for graph capability derivation from config flags."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from Config.GraphConfig import GraphConfig


def _load_module(module_name: str, relative_path: str):
    """Load one project module directly from its file path for isolated tests."""

    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BaseGraph = _load_module("graph_base_graph_capabilities_test", "Core/Graph/BaseGraph.py").BaseGraph
GraphCapability = _load_module(
    "graph_capabilities_enum_test",
    "Core/Schema/GraphCapabilities.py",
).GraphCapability


class _ConcreteBaseGraph(BaseGraph):
    """Minimal concrete subclass that exposes BaseGraph helper properties."""

    def _extract_entity_relationship(self, chunk_key_pair):
        """Unused abstract hook required for instantiation."""

        raise NotImplementedError

    def _build_graph(self, chunks):
        """Unused abstract hook required for instantiation."""

        raise NotImplementedError


def test_capabilities_follow_direct_graph_config_flags() -> None:
    """Direct GraphConfig input should control capability flags exactly."""

    graph = _ConcreteBaseGraph(
        config=GraphConfig(enable_entity_type=True, enable_edge_keywords=False),
        llm=None,
        encoder=None,
    )

    caps = graph.capabilities

    assert GraphCapability.HAS_ENTITY_TYPES in caps
    assert GraphCapability.HAS_EDGE_KEYWORDS not in caps


def test_capabilities_use_nested_graph_config_when_root_config_is_passed() -> None:
    """BaseGraph should normalize full project config to its nested graph config."""

    root_config = SimpleNamespace(
        graph=GraphConfig(enable_entity_type=False, enable_edge_keywords=True)
    )
    graph = _ConcreteBaseGraph(config=root_config, llm=None, encoder=None)

    caps = graph.capabilities

    assert GraphCapability.HAS_ENTITY_TYPES not in caps
    assert GraphCapability.HAS_EDGE_KEYWORDS in caps
