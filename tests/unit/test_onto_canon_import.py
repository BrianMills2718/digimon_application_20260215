"""Unit tests for the onto-canon6 JSONL import bridge."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from Core.Interop.onto_canon_import import import_onto_canon_jsonl


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    """Write the provided rows as one JSON object per line."""

    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_import_onto_canon_jsonl_merges_duplicates_and_skips_single_endpoint(tmp_path: Path) -> None:
    """Importer writes a DIGIMON graph artifact with deterministic merge semantics."""

    entities_path = tmp_path / "entities.jsonl"
    relationships_path = tmp_path / "relationships.jsonl"

    _write_jsonl(
        entities_path,
        [
            {
                "entity_name": "USSOCOM",
                "source_id": "ent:1",
                "entity_type": "oc:military_organization",
                "description": "",
            },
            {
                "entity_name": "USSOCOM",
                "source_id": "ent:1b",
                "entity_type": "oc:military_organization",
                "description": "Special operations command",
            },
            {
                "entity_name": "Gen. Charles R. Holland",
                "source_id": "ent:2",
                "entity_type": "oc:person",
                "description": "",
            },
        ],
    )
    _write_jsonl(
        relationships_path,
        [
            {
                "src_id": "Gen. Charles R. Holland",
                "tgt_id": "USSOCOM",
                "relation_name": "oc:hold_command_role",
                "description": "Held command role.",
                "weight": 1.0,
                "keywords": "",
                "source_id": "gassert:1",
            },
            {
                "src_id": "USSOCOM",
                "tgt_id": "Gen. Charles R. Holland",
                "relation_name": "oc:holds_leader",
                "description": "Reverse wording.",
                "weight": 0.4,
                "keywords": "",
                "source_id": "gassert:2",
            },
            {
                "src_id": "",
                "tgt_id": "USSOCOM",
                "relation_name": "oc:unary_fact",
                "description": "Missing endpoint should not be ingested.",
                "weight": 0.7,
                "keywords": "",
                "source_id": "gassert:3",
            },
        ],
    )

    result = import_onto_canon_jsonl(
        entities_path=entities_path,
        relationships_path=relationships_path,
        working_dir=tmp_path / "results",
        dataset_name="onto_canon_fixture",
        force=True,
    )

    assert result.entity_count == 2
    assert result.relationship_count == 1
    assert result.skipped_relationships_missing_endpoint == 1
    assert result.graph_path.exists()

    graph = nx.read_graphml(result.graph_path)
    assert set(graph.nodes()) == {"USSOCOM", "Gen. Charles R. Holland"}

    ussocom = graph.nodes["USSOCOM"]
    assert ussocom["entity_type"] == "oc:military_organization"
    assert "ent:1" in ussocom["source_id"]
    assert "ent:1b" in ussocom["source_id"]
    assert "Special operations command" in ussocom["description"]
    assert ussocom["canonical_name"] == "USSOCOM"
    assert "ussocom" in ussocom["search_keys"]

    edge = graph.edges[("Gen. Charles R. Holland", "USSOCOM")]
    assert edge["weight"] == 1.4
    assert "oc:hold_command_role" in edge["relation_name"]
    assert "oc:holds_leader" in edge["relation_name"]
    assert "gassert:1" in edge["source_id"]
    assert "gassert:2" in edge["source_id"]


def test_import_onto_canon_jsonl_preserves_unicode_display_name_metadata(tmp_path: Path) -> None:
    """Importer should keep Unicode display names separate from lookup metadata."""

    entities_path = tmp_path / "entities.jsonl"
    relationships_path = tmp_path / "relationships.jsonl"

    _write_jsonl(
        entities_path,
        [
            {
                "entity_name": "São José dos Campos",
                "source_id": "ent:1",
                "entity_type": "oc:place",
                "description": "Municipality in São Paulo state.",
            },
        ],
    )
    _write_jsonl(relationships_path, [])

    result = import_onto_canon_jsonl(
        entities_path=entities_path,
        relationships_path=relationships_path,
        working_dir=tmp_path / "results",
        dataset_name="onto_canon_fixture",
        force=True,
    )

    graph = nx.read_graphml(result.graph_path)
    node = graph.nodes["São José dos Campos"]

    assert node["entity_name"] == "São José dos Campos"
    assert node["canonical_name"] == "São José dos Campos"
    assert "são josé dos campos" in node["search_keys"]
    assert "sao jose dos campos" in node["search_keys"]
