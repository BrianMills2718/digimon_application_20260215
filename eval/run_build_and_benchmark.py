#!/usr/bin/env python3
"""Build the ER graph for a dataset, then run the agent benchmark.

Usage:
    python eval/run_build_and_benchmark.py --dataset HotpotQA_200 --n 200
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))


async def build_graph(dataset: str) -> bool:
    """Build ER graph for the given dataset using the configured LLM + fallbacks."""
    from Option.Config2 import Config
    from Core.Provider.LLMClientAdapter import LLMClientAdapter
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentTools.graph_construction_tools import build_er_graph, BuildERGraphInputs
    from Core.Common.Logger import logger

    config = Config.from_yaml_file("Option/Config2.yaml")

    fallback = getattr(config.llm, 'fallback_models', None) or []
    llm = LLMClientAdapter(
        config.llm.model,
        fallback_models=fallback,
        num_retries=3,
    )
    encoder = get_rag_embedding(config=config)
    chunk_factory = ChunkFactory(config)

    logger.info(f"Starting ER graph build for {dataset}")
    logger.info(f"  Model: {config.llm.model}")
    logger.info(f"  Fallbacks: {fallback}")

    start = time.time()
    tool_input = BuildERGraphInputs(
        target_dataset_name=dataset,
        force_rebuild=False,  # Resume from checkpoint if exists
    )
    result = await build_er_graph(tool_input, config, llm, encoder, chunk_factory)
    elapsed = time.time() - start

    logger.info(f"Graph build result: {result.status}")
    logger.info(f"  Nodes: {result.node_count}, Edges: {result.edge_count}")
    logger.info(f"  Time: {elapsed/60:.1f} min")
    logger.info(f"  Artifact: {result.artifact_path}")

    return result.status == "success"


def run_benchmark(dataset: str, n: int, model: str) -> None:
    """Run the agent benchmark via subprocess (it has its own argparse)."""
    import subprocess
    cmd = [
        sys.executable, "eval/run_agent_benchmark.py",
        "--dataset", dataset,
        "--n", str(n),
        "--model", model,
        "--timeout", "300",
    ]
    print(f"\n{'='*60}")
    print(f"Starting benchmark: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    subprocess.run(cmd, check=False)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="HotpotQA_200")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--model", default="gemini/gemini-3-flash-preview")
    args = parser.parse_args()

    # Step 1: Build graph
    print(f"{'='*60}")
    print(f"STEP 1: Build ER graph for {args.dataset}")
    print(f"{'='*60}")

    success = await build_graph(args.dataset)
    if not success:
        print("Graph build failed. Aborting benchmark.")
        sys.exit(1)

    # Step 2: Run benchmark
    print(f"\n{'='*60}")
    print(f"STEP 2: Run {args.n}-question agent benchmark")
    print(f"{'='*60}")

    run_benchmark(args.dataset, args.n, args.model)


if __name__ == "__main__":
    asyncio.run(main())
