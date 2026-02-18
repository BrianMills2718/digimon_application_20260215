#!/usr/bin/env python3
"""CLI entry point for running DIGIMON benchmarks.

Usage:
    python eval/run_benchmark.py --dataset HotpotQAsmallest --methods basic_local --n 10
    python eval/run_benchmark.py --dataset HotpotQA --methods basic_local,fastgraphrag,hipporag --n 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from Core.Common.Logger import logger


async def main(args: argparse.Namespace) -> None:
    from Option.Config2 import Config
    from Core.Provider.LiteLLMProvider import LiteLLMProvider
    from Core.Index.EmbeddingFactory import get_rag_embedding
    from Core.Chunk.ChunkFactory import ChunkFactory
    from Core.AgentSchema.context import GraphRAGContext
    from Core.Operators.registry import REGISTRY
    from Core.Composition.OperatorComposer import OperatorComposer

    from eval.data_prep import load_questions, get_dataset_path, check_corpus_ready, check_graph_ready
    from eval.benchmark import BenchmarkRunner
    from eval._llm_counter import CountingLLMWrapper

    # --- Init DIGIMON ---
    config_path = os.path.join(os.getcwd(), "Option", "Config2.yaml")
    config = Config.from_yaml_file(config_path)

    llm = LiteLLMProvider(config.llm)
    encoder = get_rag_embedding(config=config)
    chunk_factory = ChunkFactory(config)

    context = GraphRAGContext(
        target_dataset_name=args.dataset,
        main_config=config,
        llm_provider=llm,
        embedding_provider=encoder,
        chunk_storage_manager=chunk_factory,
    )

    # Optional agentic LLM
    agentic_llm = None
    if getattr(config, "agentic_model", None):
        try:
            from Core.Provider.LLMClientAdapter import LLMClientAdapter
            agentic_llm = LLMClientAdapter(config.agentic_model)
            logger.info(f"Agentic LLM: {config.agentic_model}")
        except ImportError:
            logger.warning("llm_client not available — using default LLM for agentic calls")

    # --- Load questions ---
    data_path = get_dataset_path(args.dataset)
    questions = load_questions(data_path, n_questions=args.num)

    # --- Check prerequisites ---
    if not check_corpus_ready(args.dataset, str(config.working_dir)):
        print(f"WARNING: Corpus not prepared for '{args.dataset}'. Run corpus_prepare first.")
    if not check_graph_ready(args.dataset, str(config.working_dir)):
        print(f"WARNING: Graph not built for '{args.dataset}'. Run graph_build_er first.")

    # --- Wrap LLM with call/token counter ---
    raw_llm = agentic_llm or llm
    counting_llm = CountingLLMWrapper(raw_llm)
    logger.info(f"LLM call counting enabled (wrapping {type(raw_llm).__name__})")

    # --- Build composer ---
    composer = OperatorComposer(REGISTRY)
    methods = [m.strip() for m in args.methods.split(",")]

    # Validate method names
    available = list(composer.profiles.keys())
    for m in methods:
        if m not in available:
            print(f"ERROR: Unknown method '{m}'. Available: {available}")
            sys.exit(1)

    # --- Build OperatorContext factory ---
    import pickle
    from Core.Operators._context import OperatorContext

    async def build_op_ctx(dataset_name: str) -> OperatorContext:
        graph = None
        entities_vdb = None
        relations_vdb = None
        doc_chunks = None
        sparse_matrices = {}
        community = None

        # Find graph
        if hasattr(context, "list_graphs"):
            for gid in context.list_graphs():
                if dataset_name in gid:
                    gi = context.get_graph_instance(gid)
                    if gi:
                        graph = gi
                        if hasattr(gi, "sparse_matrices") and gi.sparse_matrices:
                            sparse_matrices = gi.sparse_matrices
                        break

        # Try loading sparse matrices from disk
        if not sparse_matrices:
            base = Path(config.working_dir) / dataset_name / "er_graph"
            e2r_path = base / "sparse_e2r.pkl"
            r2c_path = base / "sparse_r2c.pkl"
            if e2r_path.exists() and r2c_path.exists():
                try:
                    with open(e2r_path, "rb") as f:
                        e2r = pickle.load(f)
                    with open(r2c_path, "rb") as f:
                        r2c = pickle.load(f)
                    sparse_matrices = {"entity_to_rel": e2r, "rel_to_chunk": r2c}
                except Exception as e:
                    logger.warning(f"Failed to load sparse matrices: {e}")

        # VDBs
        if hasattr(context, "list_vdbs"):
            for vdb_id in context.list_vdbs():
                vdb_inst = context.get_vdb_instance(vdb_id)
                if vdb_inst:
                    if "entities" in vdb_id and entities_vdb is None:
                        entities_vdb = vdb_inst
                    elif "relation" in vdb_id and relations_vdb is None:
                        relations_vdb = vdb_inst

        # Chunks
        if chunk_factory and doc_chunks is None:
            try:
                chunks_list = await chunk_factory.get_chunks_for_dataset(dataset_name)
                chunks_dict = {}
                for chunk_id, chunk_obj in chunks_list:
                    content = chunk_obj.content if hasattr(chunk_obj, "content") else str(chunk_obj)
                    chunks_dict[chunk_id] = content
                if chunks_dict:
                    from eval._chunk_lookup import ChunkLookup
                    doc_chunks = ChunkLookup(chunks_dict)
            except Exception as e:
                logger.warning(f"Could not load chunks: {e}")

        retriever_config = getattr(config, "retriever", config)

        return OperatorContext(
            graph=graph,
            entities_vdb=entities_vdb,
            relations_vdb=relations_vdb,
            doc_chunks=doc_chunks,
            community=community,
            llm=counting_llm,
            config=retriever_config,
            sparse_matrices=sparse_matrices,
        )

    # --- Run benchmark ---
    runner = BenchmarkRunner(
        dataset_name=args.dataset,
        methods=methods,
        questions=questions,
        composer=composer,
        op_ctx_builder=build_op_ctx,
        n_questions=args.num,
        llm_stats=counting_llm.stats,
    )
    result = await runner.run()

    # --- Save results ---
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{args.dataset}_benchmark.json"
    with open(output_path, "w") as f:
        json.dump(result.to_dict(), f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")
    print(f"\n{'='*60}")
    print(f"Dataset: {args.dataset} ({result.n_questions} questions)")
    print(f"{'='*60}")
    for name, mr in result.methods.items():
        print(f"\n{name}:")
        print(f"  EM:      {mr.avg_em:.1f}%")
        print(f"  F1:      {mr.avg_f1:.1f}%")
        print(f"  Latency: {mr.avg_latency_s:.1f}s avg")
        print(f"  LLM calls: {mr.total_llm_calls} total ({mr.avg_llm_calls_per_q:.1f}/q)")
        print(f"  Tokens: {mr.total_input_tokens + mr.total_output_tokens} total "
              f"({mr.total_input_tokens} in, {mr.total_output_tokens} out)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DIGIMON Benchmark Runner")
    parser.add_argument(
        "--dataset", required=True,
        help="Dataset name (e.g. HotpotQA, HotpotQAsmallest)",
    )
    parser.add_argument(
        "--methods", required=True,
        help="Comma-separated method names (e.g. basic_local,fastgraphrag)",
    )
    parser.add_argument(
        "--num", type=int, default=None,
        help="Limit to first N questions (default: all)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
