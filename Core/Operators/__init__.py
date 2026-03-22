"""Lazy package exports for the modular operator system.

The package previously imported every operator implementation at import time.
That made `from Core.Operators._context import OperatorContext` fragile because
Python executes this package `__init__` first, which pulled in optional
operator dependencies unrelated to context construction. The direct benchmark
backend only needs `OperatorContext`, so package import must stay side-effect
free until a specific operator export is actually requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from Core.Operators._context import OperatorContext

_OPERATOR_EXPORT_MODULES: dict[str, str] = {
    "entity_vdb": "Core.Operators.entity.vdb",
    "entity_ppr": "Core.Operators.entity.ppr",
    "entity_onehop": "Core.Operators.entity.onehop",
    "entity_link": "Core.Operators.entity.link",
    "entity_tfidf": "Core.Operators.entity.tfidf",
    "entity_agent": "Core.Operators.entity.agent",
    "entity_rel_node": "Core.Operators.entity.rel_node",
    "relationship_onehop": "Core.Operators.relationship.onehop",
    "relationship_vdb": "Core.Operators.relationship.vdb",
    "relationship_score_agg": "Core.Operators.relationship.score_aggregator",
    "relationship_agent": "Core.Operators.relationship.agent",
    "chunk_from_relation": "Core.Operators.chunk.from_relation",
    "chunk_occurrence": "Core.Operators.chunk.occurrence",
    "chunk_aggregator": "Core.Operators.chunk.aggregator",
    "subgraph_khop_paths": "Core.Operators.subgraph.khop_paths",
    "subgraph_steiner_tree": "Core.Operators.subgraph.steiner_tree",
    "subgraph_agent_path": "Core.Operators.subgraph.agent_path",
    "community_from_entity": "Core.Operators.community.from_entity",
    "community_from_level": "Core.Operators.community.from_level",
    "meta_extract_entities": "Core.Operators.meta.extract_entities",
    "meta_reason_step": "Core.Operators.meta.reason_step",
    "meta_rerank": "Core.Operators.meta.rerank",
    "meta_generate_answer": "Core.Operators.meta.generate_answer",
    "meta_pcst_optimize": "Core.Operators.meta.pcst_optimize",
}

__all__ = ["OperatorContext", *_OPERATOR_EXPORT_MODULES.keys()]


def __getattr__(name: str) -> Any:
    """Resolve operator exports lazily so optional deps are imported on demand."""

    if name == "OperatorContext":
        return OperatorContext
    module_path = _OPERATOR_EXPORT_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path)
    return getattr(module, name)
