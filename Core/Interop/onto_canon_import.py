"""Import onto-canon6 JSONL exports into DIGIMON's native graph storage.

The onto-canon6 adapter already exports promoted assertions as flat
``EntityRecord`` and ``RelationshipRecord`` JSONL. DIGIMON did not yet have a
consumer-side importer that materializes those records into the persisted
NetworkX graph format its operators load today. This module provides that thin
bridge so cross-project data flow can be exercised on real governed data
without routing back through DIGIMON's LLM extraction pipeline.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import networkx as nx

from Core.Common.entity_name_hygiene import build_identity_payload
from Core.Schema.SlotTypes import EntityRecord, RelationshipRecord

GRAPH_FIELD_SEP = "<SEP>"
GRAPH_FILE_NAME = "nx_data.graphml"


@dataclass(frozen=True)
class OntoCanonImportResult:
    """Summarize one onto-canon6 JSONL import into DIGIMON storage."""

    dataset_name: str
    graph_namespace: str
    graph_path: Path
    entity_count: int
    relationship_count: int
    skipped_relationships_missing_endpoint: int


def load_entity_records(path: Path) -> list[EntityRecord]:
    """Load DIGIMON-shaped entity records from JSONL."""

    rows = _load_jsonl(path)
    return [
        EntityRecord(
            entity_name=str(row["entity_name"]),
            source_id=str(row.get("source_id", "")),
            entity_type=str(row.get("entity_type", "")),
            description=str(row.get("description", "")),
            rank=int(row.get("rank", 0) or 0),
        )
        for row in rows
    ]


def load_relationship_records(path: Path) -> list[RelationshipRecord]:
    """Load DIGIMON-shaped relationship records from JSONL."""

    rows = _load_jsonl(path)
    return [
        RelationshipRecord(
            src_id=str(row.get("src_id", "")),
            tgt_id=str(row.get("tgt_id", "")),
            relation_name=str(row.get("relation_name", "")),
            description=str(row.get("description", "")),
            weight=float(row.get("weight", 0.0) or 0.0),
            keywords=str(row.get("keywords", "")),
            source_id=str(row.get("source_id", "")),
        )
        for row in rows
    ]


def import_onto_canon_jsonl(
    *,
    entities_path: Path,
    relationships_path: Path,
    working_dir: Path,
    dataset_name: str,
    graph_namespace: str = "er_graph",
    force: bool = False,
) -> OntoCanonImportResult:
    """Materialize onto-canon6 export JSONL into DIGIMON graph storage.

    The output graph is written to ``<working_dir>/<dataset_name>/<graph_namespace>/``
    as DIGIMON's native GraphML artifact. This importer intentionally fails loud
    when the target graph already exists unless ``force=True`` is requested.
    """

    entities = load_entity_records(entities_path)
    relationships = load_relationship_records(relationships_path)
    return _import_records(
        entities=entities,
        relationships=relationships,
        working_dir=working_dir,
        dataset_name=dataset_name,
        graph_namespace=graph_namespace,
        force=force,
    )


def _import_records(
    *,
    entities: list[EntityRecord],
    relationships: list[RelationshipRecord],
    working_dir: Path,
    dataset_name: str,
    graph_namespace: str,
    force: bool,
) -> OntoCanonImportResult:
    """Write the provided entity and relationship records into graph storage."""

    graph_path = _graph_path(
        working_dir=working_dir,
        dataset_name=dataset_name,
        graph_namespace=graph_namespace,
    )

    if graph_path.exists() and not force:
        raise ValueError(
            f"Refusing to overwrite existing DIGIMON graph artifact: {graph_path}. "
            "Pass force=True to rebuild it."
        )

    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph = nx.Graph()

    merged_entities = _merge_entities(entities)
    for entity_name, node_data in merged_entities.items():
        graph.add_node(entity_name, **node_data)

    merged_relationships, skipped_missing_endpoint = _merge_relationships(relationships)
    for (src_id, tgt_id), edge_data in merged_relationships.items():
        for node_id in (src_id, tgt_id):
            if graph.has_node(node_id):
                continue
            graph.add_node(
                node_id,
                entity_name=node_id,
                source_id=edge_data["source_id"],
                entity_type="",
                description="",
            )
        graph.add_edge(src_id, tgt_id, **edge_data)

    nx.write_graphml(graph, graph_path)
    return OntoCanonImportResult(
        dataset_name=dataset_name,
        graph_namespace=graph_namespace,
        graph_path=graph_path,
        entity_count=len(merged_entities),
        relationship_count=len(merged_relationships),
        skipped_relationships_missing_endpoint=skipped_missing_endpoint,
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load one JSON object per line and reject malformed input loudly."""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object per line")
            rows.append(row)
    return rows


def _merge_entities(entities: list[EntityRecord]) -> dict[str, dict[str, Any]]:
    """Merge duplicate entity rows by entity_name for graph-node storage."""

    grouped: dict[str, list[EntityRecord]] = defaultdict(list)
    for entity in entities:
        if not entity.entity_name.strip():
            raise ValueError("Imported entity names must be non-empty")
        grouped[entity.entity_name].append(entity)

    merged: dict[str, dict[str, Any]] = {}
    for entity_name, records in grouped.items():
        entity_type = _most_common_non_empty(record.entity_type for record in records)
        identity_payload = build_identity_payload(
            [entity_name],
            fallback_entity_name=entity_name,
            include_aliases=False,
        )
        merged[entity_name] = {
            "entity_name": entity_name,
            "source_id": _join_unique(record.source_id for record in records),
            "entity_type": entity_type,
            "description": _join_unique(record.description for record in records),
            **identity_payload,
        }
    return merged


def _merge_relationships(
    relationships: list[RelationshipRecord],
) -> tuple[dict[tuple[str, str], dict[str, Any]], int]:
    """Merge duplicate relationship rows by undirected endpoint pair."""

    grouped: dict[tuple[str, str], list[RelationshipRecord]] = defaultdict(list)
    skipped_missing_endpoint = 0

    for relationship in relationships:
        if not relationship.src_id or not relationship.tgt_id:
            skipped_missing_endpoint += 1
            continue

        src_id, tgt_id = sorted((relationship.src_id, relationship.tgt_id))
        grouped[(src_id, tgt_id)].append(relationship)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for (src_id, tgt_id), records in grouped.items():
        merged[(src_id, tgt_id)] = {
            "src_id": src_id,
            "tgt_id": tgt_id,
            "source_id": _join_unique(record.source_id for record in records),
            "relation_name": _join_unique(record.relation_name for record in records),
            "keywords": _join_unique(record.keywords for record in records),
            "description": _join_unique(record.description for record in records),
            "weight": sum(record.weight for record in records),
        }
    return merged, skipped_missing_endpoint


def _join_unique(values: Any) -> str:
    """Join distinct non-empty values with DIGIMON's field separator."""

    parts = sorted({str(value).strip() for value in values if str(value).strip()})
    return GRAPH_FIELD_SEP.join(parts)


def _most_common_non_empty(values: Any) -> str:
    """Return the most frequent non-empty string or an empty fallback."""

    non_empty = [str(value).strip() for value in values if str(value).strip()]
    if not non_empty:
        return ""
    return Counter(non_empty).most_common(1)[0][0]


def _graph_path(*, working_dir: Path, dataset_name: str, graph_namespace: str) -> Path:
    """Return the persisted GraphML path for the requested DIGIMON artifact."""

    return working_dir / dataset_name / graph_namespace / GRAPH_FILE_NAME


__all__ = [
    "OntoCanonImportResult",
    "import_onto_canon_jsonl",
    "load_entity_records",
    "load_relationship_records",
]
