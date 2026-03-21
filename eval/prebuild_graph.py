#!/usr/bin/env python3
"""Pre-build graph artifacts for a dataset before running benchmarks.

This script is the operational entrypoint for profile-aware entity-graph
rebuilds. It keeps the existing "build graph + VDBs" workflow, but adds a
typed CLI for graph-profile/schema overrides and an explicit chunk-limit for
small-slice validation runs.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import llm_client  # noqa: F401  # Triggers API key auto-load from ~/.secrets/api_keys.env.

from Core.AgentSchema.graph_construction_tool_contracts import (
    BuildERGraphInputs,
    ERGraphConfigOverrides,
)
from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode

ENTITY_GRAPH_PROFILES = (
    GraphProfile.KG.value.lower(),
    GraphProfile.TKG.value.lower(),
    GraphProfile.RKG.value.lower(),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the prebuild CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Pre-build a DIGIMON graph and optional VDB artifacts.",
    )
    parser.add_argument("dataset", help="Dataset name, for example MuSiQue or HotpotQA_full.")
    parser.add_argument(
        "--artifact-dataset-name",
        help="Optional artifact namespace. Defaults to the source dataset name.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Rebuild graph artifacts even if they already exist on disk.",
    )
    parser.add_argument(
        "--graph-profile",
        choices=list(ENTITY_GRAPH_PROFILES),
        help="Explicit graph profile to build, such as kg, tkg, or rkg.",
    )
    parser.add_argument(
        "--schema-mode",
        choices=[mode.value for mode in GraphSchemaMode],
        help="Schema guidance mode for extraction: open, guided, or closed.",
    )
    parser.add_argument(
        "--schema-entity-type",
        action="append",
        default=[],
        help="Allowed entity type for guided/closed extraction. Repeat the flag for multiple values.",
    )
    parser.add_argument(
        "--schema-relation-type",
        action="append",
        default=[],
        help="Allowed relation type for guided/closed extraction. Repeat the flag for multiple values.",
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=None,
        help="Optional cap on how many prepared chunks to include in the graph build.",
    )
    parser.add_argument(
        "--skip-entity-vdb",
        action="store_true",
        help="Skip the entity VDB build step.",
    )
    parser.add_argument(
        "--skip-relationship-vdb",
        action="store_true",
        help="Skip the relationship VDB build step.",
    )
    return parser.parse_args(argv)


def build_er_config_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Translate CLI flags into ER graph config overrides.

    The script fails loudly if schema types are provided without an explicit
    schema mode. That combination is ambiguous and should be made deliberate.
    """

    if args.chunk_limit is not None and args.chunk_limit < 1:
        raise ValueError("--chunk-limit must be at least 1")

    if (args.schema_entity_type or args.schema_relation_type) and args.schema_mode is None:
        raise ValueError(
            "Schema types require --schema-mode guided or --schema-mode closed"
        )

    overrides: dict[str, Any] = {}
    if args.graph_profile is not None:
        overrides["graph_profile"] = GraphProfile(args.graph_profile.upper())
    if args.schema_mode is not None:
        overrides["schema_mode"] = GraphSchemaMode(args.schema_mode)
    if args.schema_entity_type:
        overrides["schema_entity_types"] = list(args.schema_entity_type)
    if args.schema_relation_type:
        overrides["schema_relation_types"] = list(args.schema_relation_type)
    return overrides


def build_requires_fresh_graph(args: argparse.Namespace) -> bool:
    """Return whether the requested CLI contract must not reuse an old graph."""

    return any(
        [
            args.graph_profile is not None,
            args.schema_mode is not None,
            bool(args.schema_entity_type),
            bool(args.schema_relation_type),
            args.chunk_limit is not None,
        ]
    )


def ensure_existing_graph_can_be_reused(args: argparse.Namespace, graph_path: Path) -> None:
    """Fail loudly if a stale on-disk graph would violate the requested contract."""

    if not graph_path.exists():
        return

    if args.force_rebuild:
        return

    if build_requires_fresh_graph(args):
        raise ValueError(
            "Graph already exists on disk, but this run requested an explicit "
            "build contract. Re-run with --force-rebuild so the graph and "
            "manifest match the requested profile/schema/slice."
        )


def resolve_artifact_dataset_name(args: argparse.Namespace) -> str:
    """Return the artifact namespace for this CLI run."""

    return args.artifact_dataset_name or args.dataset


async def main(args: argparse.Namespace) -> None:
    """Run the requested graph build and optional VDB build steps."""

    import digimon_mcp_stdio_server as server
    from Core.AgentTools.graph_construction_tools import build_er_graph

    await server._ensure_initialized()
    await server._ensure_corpus(args.dataset, None)
    print(f"Initialized. LLM model: {server._state['config'].llm.model}")

    artifact_dataset_name = resolve_artifact_dataset_name(args)
    graph_path = (
        Path(server._state["config"].working_dir)
        / artifact_dataset_name
        / "er_graph"
        / "nx_data.graphml"
    )
    ensure_existing_graph_can_be_reused(args, graph_path)

    overrides_dict = build_er_config_overrides(args)
    overrides = ERGraphConfigOverrides(**overrides_dict) if overrides_dict else None

    print(
        "[1/3] Building ER graph with "
        f"source_dataset={args.dataset}, "
        f"artifact_dataset={artifact_dataset_name}, "
        f"profile={args.graph_profile or 'default'}, "
        f"schema_mode={args.schema_mode or 'default'}, "
        f"chunk_limit={args.chunk_limit or 'all'}..."
    )
    t0 = time.time()
    server._tag_llm_for_build("er", artifact_dataset_name)
    result = await build_er_graph(
        BuildERGraphInputs(
            target_dataset_name=args.dataset,
            artifact_dataset_name=artifact_dataset_name,
            force_rebuild=args.force_rebuild,
            chunk_limit=args.chunk_limit,
            config_overrides=overrides,
        ),
        server._state["config"],
        server._state["llm"],
        server._state["encoder"],
        server._state["chunk_factory"],
    )
    elapsed = time.time() - t0
    if result.status != "success":
        raise RuntimeError(
            f"ER graph build failed in {elapsed:.0f}s: {result.message}"
        )
    await server._register_graph_if_built(result)
    print(
        f"[1/3] Graph build done in {elapsed:.0f}s: "
        f"nodes={result.node_count} edges={result.edge_count} artifact={result.artifact_path}"
    )

    if args.skip_entity_vdb:
        print("[2/3] Skipping entity VDB build.")
    else:
        print("[2/3] Building entity VDB...")
        t0 = time.time()
        entity_result = await server.entity_vdb_build(
            graph_reference_id=f"{artifact_dataset_name}_ERGraph",
            vdb_collection_name=f"{artifact_dataset_name}_entities",
            force_rebuild=args.force_rebuild,
        )
        elapsed = time.time() - t0
        print(f"[2/3] Entity VDB done in {elapsed:.0f}s: {entity_result[:200]}")

    if args.skip_relationship_vdb:
        print("[3/3] Skipping relationship VDB build.")
    else:
        print("[3/3] Building relationship VDB...")
        t0 = time.time()
        relationship_result = await server.relationship_vdb_build(
            graph_reference_id=f"{artifact_dataset_name}_ERGraph",
            vdb_collection_name=f"{artifact_dataset_name}_relationships_vdb_relationships",
            force_rebuild=args.force_rebuild,
        )
        elapsed = time.time() - t0
        print(f"[3/3] Relationship VDB done in {elapsed:.0f}s: {relationship_result[:200]}")

    print(
        "\nAll requested prerequisites built for "
        f"source_dataset={args.dataset} artifact_dataset={artifact_dataset_name}."
    )


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
