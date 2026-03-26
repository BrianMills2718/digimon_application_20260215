#!/usr/bin/env python3
"""CLI wrapper for importing onto-canon6 JSONL exports into DIGIMON storage."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Core.Interop.onto_canon_import import import_onto_canon_jsonl


def parse_args() -> argparse.Namespace:
    """Parse the importer's command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Import onto-canon6 DIGIMON JSONL export into persisted graph storage.",
    )
    parser.add_argument("--entities", required=True, type=Path, help="Path to entities.jsonl.")
    parser.add_argument(
        "--relationships",
        required=True,
        type=Path,
        help="Path to relationships.jsonl.",
    )
    parser.add_argument(
        "--working-dir",
        type=Path,
        default=PROJECT_ROOT / "results",
        help="DIGIMON artifact root where the graph should be written.",
    )
    parser.add_argument(
        "--dataset-name",
        required=True,
        help="Artifact dataset namespace to create under the working directory.",
    )
    parser.add_argument(
        "--graph-namespace",
        default="er_graph",
        help="Graph namespace folder under the dataset artifact directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing graph artifact instead of failing.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the onto-canon6 JSONL import and print a compact summary."""

    args = parse_args()
    result = import_onto_canon_jsonl(
        entities_path=args.entities,
        relationships_path=args.relationships,
        working_dir=args.working_dir,
        dataset_name=args.dataset_name,
        graph_namespace=args.graph_namespace,
        force=args.force,
    )
    print(
        f"Imported {result.entity_count} entities and {result.relationship_count} relationships "
        f"into {result.graph_path}"
    )
    if result.skipped_relationships_missing_endpoint:
        print(
            "Skipped "
            f"{result.skipped_relationships_missing_endpoint} relationships with a missing endpoint."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
