"""Build persisted graph artifacts from prepared chunk corpora.

These helpers are the build-time contract behind DIGIMON's graph-construction
tools. They accept typed tool inputs, apply graph-config overrides, execute the
requested build, and persist a manifest describing what was actually built.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from Core.AgentSchema.graph_construction_tool_contracts import (
    BuildERGraphInputs, BuildERGraphOutputs, ERGraphConfigOverrides,
    BuildRKGraphInputs, BuildRKGraphOutputs, RKGraphConfigOverrides,
    BuildTreeGraphInputs, BuildTreeGraphOutputs, TreeGraphConfigOverrides,
    BuildTreeGraphBalancedInputs, BuildTreeGraphBalancedOutputs, TreeGraphBalancedConfigOverrides,
    BuildPassageGraphInputs, BuildPassageGraphOutputs, PassageGraphConfigOverrides,
)
from Core.Graph.GraphFactory import get_graph
from Option.Config2 import Config
from Core.Common.Logger import logger
from Core.Schema.GraphBuildManifest import write_graph_build_manifest


def apply_overrides(config_copy: Any, overrides: Optional[Any]) -> None:
    """Apply typed override values onto a copied config object.

    This fails loudly on unknown fields so graph builds do not silently ignore
    contract drift between tool schemas and the underlying config model.
    """

    if not overrides:
        logger.info("apply_overrides: No overrides provided, skipping")
        return

    if hasattr(overrides, "model_dump"):
        override_dict = overrides.model_dump(exclude_unset=True)
    else:
        override_dict = overrides.dict(exclude_unset=True)

    logger.debug(f"apply_overrides: Applying overrides {override_dict}")

    for field_name, value in override_dict.items():
        if not hasattr(config_copy, field_name):
            raise AttributeError(
                f"Graph config has no field '{field_name}' for override type "
                f"{type(overrides).__name__}"
            )
        setattr(config_copy, field_name, value)
        logger.debug(f"apply_overrides: Set {field_name}={value} on config")


def get_artifact_path(graph_instance: Any) -> str | None:
    """Return the persisted artifact directory for a built graph instance."""

    if hasattr(graph_instance._graph, 'namespace') and hasattr(graph_instance._graph.namespace, 'path'):
        return str(graph_instance._graph.namespace.path)

    if hasattr(graph_instance._graph, 'file_path'):
        return str(Path(graph_instance._graph.file_path).parent)

    if hasattr(graph_instance._graph, 'tree_pkl_file'):
        return str(Path(graph_instance._graph.tree_pkl_file).parent)

    return None


async def get_graph_counts(graph_instance: Any) -> dict[str, int | None]:
    """Collect basic size metrics from a graph instance or its storage layer."""

    node_count = None
    edge_count = None
    layer_count = None

    if hasattr(graph_instance, 'node_num'):
        node_count = graph_instance.node_num
        if asyncio.iscoroutinefunction(graph_instance.node_num):
            node_count = await graph_instance.node_num()
        elif callable(graph_instance.node_num):
            node_count = graph_instance.node_num()
    elif hasattr(graph_instance._graph, 'get_node_num'):
        node_count = graph_instance._graph.get_node_num()
    if hasattr(graph_instance, 'edge_num'):
        edge_count = graph_instance.edge_num
        if asyncio.iscoroutinefunction(graph_instance.edge_num):
            edge_count = await graph_instance.edge_num()
        elif callable(graph_instance.edge_num):
            edge_count = graph_instance.edge_num()
    elif hasattr(graph_instance._graph, 'get_edge_num'):
        edge_count = graph_instance._graph.get_edge_num()
    if hasattr(graph_instance, 'num_layers'):
        layer_count = graph_instance.num_layers
        if asyncio.iscoroutinefunction(graph_instance.num_layers):
            layer_count = await graph_instance.num_layers()
        elif callable(graph_instance.num_layers):
            layer_count = graph_instance.num_layers()
    elif hasattr(graph_instance._graph, 'get_layer_num'):
        layer_count = graph_instance._graph.get_layer_num()
    return dict(node_count=node_count, edge_count=edge_count, layer_count=layer_count)


def _select_input_chunks(
    input_chunks: list[Any],
    chunk_limit: int | None,
    dataset_name: str,
) -> tuple[list[Any], int]:
    """Return the selected build slice while keeping observability explicit."""

    available_count = len(input_chunks)
    if chunk_limit is None:
        return input_chunks, available_count

    selected_chunks = input_chunks[:chunk_limit]
    logger.info(
        f"Selecting {len(selected_chunks)}/{available_count} chunks "
        f"for graph build dataset={dataset_name}"
    )
    return selected_chunks, available_count


async def build_er_graph(
    tool_input: BuildERGraphInputs,
    main_config: Config,
    llm_instance: Any,
    encoder_instance: Any,
    chunk_factory: Any
) -> BuildERGraphOutputs:
    """Build an entity graph from prepared chunks and persist its manifest."""

    try:
        current_graph_config = main_config.graph.model_copy(deep=True)
        apply_overrides(current_graph_config, tool_input.config_overrides)
        temp_full_config = main_config.model_copy(deep=True)
        temp_full_config.graph = current_graph_config
        temp_full_config.graph.type = "er_graph"
        er_graph_instance = get_graph(
            config=temp_full_config,
            llm=llm_instance,
            encoder=encoder_instance,
        )
        if hasattr(er_graph_instance._graph, 'namespace'):
            er_graph_instance._graph.namespace = chunk_factory.get_namespace(tool_input.target_dataset_name, graph_type="er_graph")
        input_chunks = await chunk_factory.get_chunks_for_dataset(tool_input.target_dataset_name)
        if not input_chunks:
            return BuildERGraphOutputs(
                graph_id="", status="failure",
                message=f"No input chunks found for dataset: {tool_input.target_dataset_name}",
                artifact_path=None
            )

        selected_chunks, available_input_chunk_count = _select_input_chunks(
            input_chunks=input_chunks,
            chunk_limit=tool_input.chunk_limit,
            dataset_name=tool_input.target_dataset_name,
        )
        logger.info(f"Calling er_graph_instance.build_graph for dataset: {tool_input.target_dataset_name}")
        success = await er_graph_instance.build_graph(
            chunks=selected_chunks,
            force=tool_input.force_rebuild,
        )

        if not success:
            logger.error(f"build_er_graph tool: er_graph_instance.build_graph failed for {tool_input.target_dataset_name}")
            return BuildERGraphOutputs(
                graph_id=f"{tool_input.target_dataset_name}_ERGraph",
                status="failure",
                message=f"ERGraph building failed internally for {tool_input.target_dataset_name}.",
                node_count=None,
                edge_count=None,
                artifact_path=None
            )
        
        logger.info(f"build_er_graph tool: er_graph_instance.build_graph succeeded for {tool_input.target_dataset_name}")
        counts = await get_graph_counts(er_graph_instance)
        artifact_p = get_artifact_path(er_graph_instance)
        if artifact_p is None:
            raise ValueError("ERGraph build succeeded but did not produce an artifact path")
        write_graph_build_manifest(
            dataset_name=tool_input.target_dataset_name,
            graph_type="er_graph",
            graph_config=current_graph_config,
            artifact_path=artifact_p,
            available_input_chunk_count=available_input_chunk_count,
            selected_input_chunk_count=len(selected_chunks),
            requested_input_chunk_limit=tool_input.chunk_limit,
        )

        logger.info(f"build_er_graph artifact path: {artifact_p}")

        return BuildERGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_ERGraph",
            status="success",
            message=f"ERGraph built successfully for {tool_input.target_dataset_name}.",
            node_count=counts['node_count'],
            edge_count=counts['edge_count'],
            layer_count=counts['layer_count'],
            artifact_path=artifact_p,
            graph_instance=er_graph_instance
        )
    except Exception as e:
        return BuildERGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_ERGraph",
            status="failure",
            message=str(e),
            artifact_path=None
        )


async def build_rk_graph(
    tool_input: BuildRKGraphInputs,
    main_config: Config,
    llm_instance: Any,
    encoder_instance: Any,
    chunk_factory: Any
) -> BuildRKGraphOutputs:
    """Build a keyword-rich entity graph from prepared chunks."""

    try:
        current_graph_config = main_config.graph.model_copy(deep=True)
        apply_overrides(current_graph_config, tool_input.config_overrides)
        temp_full_config = main_config.model_copy(deep=True)
        temp_full_config.graph = current_graph_config
        temp_full_config.graph.type = "rkg_graph"
        rk_graph_instance = get_graph(
            config=temp_full_config,
            llm=llm_instance,
            encoder=encoder_instance,
        )
        if hasattr(rk_graph_instance._graph, 'namespace'):
            rk_graph_instance._graph.namespace = chunk_factory.get_namespace(tool_input.target_dataset_name, graph_type="rkg_graph")
        input_chunks = await chunk_factory.get_chunks_for_dataset(tool_input.target_dataset_name)
        if not input_chunks:
            return BuildRKGraphOutputs(
                graph_id="", status="failure",
                message=f"No input chunks found for dataset: {tool_input.target_dataset_name}",
                artifact_path=None
            )
        await rk_graph_instance.build_graph(chunks=input_chunks, force=tool_input.force_rebuild)
        counts = await get_graph_counts(rk_graph_instance)
        artifact_p = get_artifact_path(rk_graph_instance)
        if artifact_p is None:
            raise ValueError("RKGraph build succeeded but did not produce an artifact path")
        write_graph_build_manifest(
            dataset_name=tool_input.target_dataset_name,
            graph_type="rkg_graph",
            graph_config=current_graph_config,
            artifact_path=artifact_p,
            available_input_chunk_count=len(input_chunks),
            selected_input_chunk_count=len(input_chunks),
        )
        return BuildRKGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_RKGraph",
            status="success",
            message=f"RKGraph built successfully for {tool_input.target_dataset_name}.",
            node_count=counts['node_count'],
            edge_count=counts['edge_count'],
            layer_count=counts['layer_count'],
            artifact_path=artifact_p
        )
    except Exception as e:
        return BuildRKGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_RKGraph",
            status="failure",
            message=str(e),
            artifact_path=None
        )


async def build_tree_graph(
    tool_input: BuildTreeGraphInputs,
    main_config: Config,
    llm_instance: Any,
    encoder_instance: Any,
    chunk_factory: Any
) -> BuildTreeGraphOutputs:
    """Build a hierarchical tree graph from prepared chunks."""

    try:
        current_graph_config = main_config.graph.model_copy(deep=True)
        apply_overrides(current_graph_config, tool_input.config_overrides)
        temp_full_config = main_config.model_copy(deep=True)
        temp_full_config.graph = current_graph_config
        temp_full_config.graph.type = "tree_graph"
        tree_graph_instance = get_graph(
            config=temp_full_config,
            llm=llm_instance,
            encoder=encoder_instance,
        )
        if hasattr(tree_graph_instance._graph, 'namespace'):
            tree_graph_instance._graph.namespace = chunk_factory.get_namespace(tool_input.target_dataset_name, graph_type="tree_graph")
        input_chunks = await chunk_factory.get_chunks_for_dataset(tool_input.target_dataset_name)
        if not input_chunks:
            return BuildTreeGraphOutputs(
                graph_id="", status="failure",
                message=f"No input chunks found for dataset: {tool_input.target_dataset_name}",
                artifact_path=None
            )
        await tree_graph_instance.build_graph(chunks=input_chunks, force=tool_input.force_rebuild)
        counts = await get_graph_counts(tree_graph_instance)
        artifact_p = get_artifact_path(tree_graph_instance)
        if artifact_p is None:
            raise ValueError("TreeGraph build succeeded but did not produce an artifact path")
        write_graph_build_manifest(
            dataset_name=tool_input.target_dataset_name,
            graph_type="tree_graph",
            graph_config=current_graph_config,
            artifact_path=artifact_p,
            available_input_chunk_count=len(input_chunks),
            selected_input_chunk_count=len(input_chunks),
        )
        return BuildTreeGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_TreeGraph",
            status="success",
            message=f"TreeGraph built successfully for {tool_input.target_dataset_name}.",
            node_count=counts['node_count'],
            edge_count=counts['edge_count'],
            layer_count=counts['layer_count'],
            artifact_path=artifact_p
        )
    except Exception as e:
        return BuildTreeGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_TreeGraph",
            status="failure",
            message=str(e),
            artifact_path=None
        )


async def build_tree_graph_balanced(
    tool_input: BuildTreeGraphBalancedInputs,
    main_config: Config,
    llm_instance: Any,
    encoder_instance: Any,
    chunk_factory: Any
) -> BuildTreeGraphBalancedOutputs:
    """Build a balanced hierarchical tree graph from prepared chunks."""

    try:
        current_graph_config = main_config.graph.model_copy(deep=True)
        apply_overrides(current_graph_config, tool_input.config_overrides)
        temp_full_config = main_config.model_copy(deep=True)
        temp_full_config.graph = current_graph_config
        temp_full_config.graph.type = "tree_graph_balanced"
        tree_graph_balanced_instance = get_graph(
            config=temp_full_config,
            llm=llm_instance,
            encoder=encoder_instance,
        )
        if hasattr(tree_graph_balanced_instance._graph, 'namespace'):
            tree_graph_balanced_instance._graph.namespace = chunk_factory.get_namespace(tool_input.target_dataset_name, graph_type="tree_graph_balanced")
        input_chunks = await chunk_factory.get_chunks_for_dataset(tool_input.target_dataset_name)
        if not input_chunks:
            return BuildTreeGraphBalancedOutputs(
                graph_id="", status="failure",
                message=f"No input chunks found for dataset: {tool_input.target_dataset_name}",
                artifact_path=None
            )
        await tree_graph_balanced_instance.build_graph(chunks=input_chunks, force=tool_input.force_rebuild)
        counts = await get_graph_counts(tree_graph_balanced_instance)
        artifact_p = get_artifact_path(tree_graph_balanced_instance)
        if artifact_p is None:
            raise ValueError("TreeGraphBalanced build succeeded but did not produce an artifact path")
        write_graph_build_manifest(
            dataset_name=tool_input.target_dataset_name,
            graph_type="tree_graph_balanced",
            graph_config=current_graph_config,
            artifact_path=artifact_p,
            available_input_chunk_count=len(input_chunks),
            selected_input_chunk_count=len(input_chunks),
        )
        return BuildTreeGraphBalancedOutputs(
            graph_id=f"{tool_input.target_dataset_name}_TreeGraphBalanced",
            status="success",
            message=f"TreeGraphBalanced built successfully for {tool_input.target_dataset_name}.",
            node_count=counts['node_count'],
            edge_count=counts['edge_count'],
            layer_count=counts['layer_count'],
            artifact_path=artifact_p
        )
    except Exception as e:
        return BuildTreeGraphBalancedOutputs(
            graph_id=f"{tool_input.target_dataset_name}_TreeGraphBalanced",
            status="failure",
            message=str(e),
            artifact_path=None
        )


async def build_passage_graph(
    tool_input: BuildPassageGraphInputs,
    main_config: Config,
    llm_instance: Any,
    encoder_instance: Any,
    chunk_factory: Any
) -> BuildPassageGraphOutputs:
    """Build a passage graph from prepared chunks."""

    try:
        current_graph_config = main_config.graph.model_copy(deep=True)
        apply_overrides(current_graph_config, tool_input.config_overrides)
        temp_full_config = main_config.model_copy(deep=True)
        temp_full_config.graph = current_graph_config
        temp_full_config.graph.type = "passage_graph"
        passage_graph_instance = get_graph(
            config=temp_full_config,
            llm=llm_instance,
            encoder=encoder_instance,
        )
        if hasattr(passage_graph_instance._graph, 'namespace'):
            passage_graph_instance._graph.namespace = chunk_factory.get_namespace(tool_input.target_dataset_name, graph_type="passage_of_graph")
        input_chunks = await chunk_factory.get_chunks_for_dataset(tool_input.target_dataset_name)
        if not input_chunks:
            return BuildPassageGraphOutputs(
                graph_id="", status="failure",
                message=f"No input chunks found for dataset: {tool_input.target_dataset_name}",
                artifact_path=None
            )
        await passage_graph_instance.build_graph(chunks=input_chunks, force=tool_input.force_rebuild)
        counts = await get_graph_counts(passage_graph_instance)
        artifact_p = get_artifact_path(passage_graph_instance)
        if artifact_p is None:
            raise ValueError("PassageGraph build succeeded but did not produce an artifact path")
        write_graph_build_manifest(
            dataset_name=tool_input.target_dataset_name,
            graph_type="passage_graph",
            graph_config=current_graph_config,
            artifact_path=artifact_p,
            available_input_chunk_count=len(input_chunks),
            selected_input_chunk_count=len(input_chunks),
        )
        return BuildPassageGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_PassageGraph",
            status="success",
            message=f"PassageGraph built successfully for {tool_input.target_dataset_name}.",
            node_count=counts['node_count'],
            edge_count=counts['edge_count'],
            layer_count=counts['layer_count'],
            artifact_path=artifact_p
        )
    except Exception as e:
        return BuildPassageGraphOutputs(
            graph_id=f"{tool_input.target_dataset_name}_PassageGraph",
            status="failure",
            message=str(e),
            artifact_path=None
        )
