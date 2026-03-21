"""Chunk VDB Build Tool — creates a FAISS vector index over document chunks.

Supports three embedding modes (configurable via ChunkConfig.vdb_embedding_mode):
- text_only: embed chunk text directly (default, current behavior)
- questions_only: generate hypothetical questions per chunk at build time,
  embed those. Query-time matching is question-to-question (HyPE pattern).
- hybrid: embed both chunk text and generated questions, maximizing recall.

Inspired by EcphoryRAG's dual retrieval and HyPE (Hypothetical Prompt Embeddings).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from Core.AgentSchema.context import GraphRAGContext
from Core.Index.FaissIndex import FaissIndex
from Core.Common.Logger import logger
from Core.AgentTools.index_config_helper import create_faiss_index_config

_hype_logger = logging.getLogger(__name__)


async def _generate_hypothetical_questions(
    chunk_id: str,
    chunk_text: str,
    n_questions: int,
    model: str,
) -> list[str]:
    """Generate hypothetical questions that a chunk would answer.

    Uses an LLM to produce questions whose embeddings will be close
    to user queries about the same topic, bridging vocabulary gaps.
    """
    from llm_client import acall_llm
    from llm_client import render_prompt

    try:
        messages = render_prompt(
            "prompts/hype_generate_questions.yaml",
            passage=chunk_text[:1500],
            n_questions=n_questions,
        )
    except Exception:
        # Fallback if prompt template doesn't exist yet
        messages = [{"role": "user", "content": (
            f"Given this text passage, generate exactly {n_questions} diverse questions "
            f"that this passage directly answers. Each question should use different "
            f"vocabulary and phrasing. Return only the questions, one per line.\n\n"
            f"Passage:\n{chunk_text[:1500]}"
        )}]

    try:
        result = await acall_llm(
            model,
            messages,
            task="digimon.hype.generate_questions",
            trace_id=f"hype.{chunk_id}",
            max_budget=0,
        )
        lines = [
            line.strip().lstrip("0123456789.-) ")
            for line in result.content.strip().split("\n")
            if line.strip() and len(line.strip()) > 10
        ]
        return lines[:n_questions]
    except Exception as e:
        _hype_logger.warning("HyPE question generation failed for %s: %s", chunk_id, e)
        return []


def _load_cached_questions(cache_path: str) -> dict[str, list[str]] | None:
    """Load previously generated questions from cache file."""
    import json
    from pathlib import Path
    p = Path(cache_path)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception as e:
        _hype_logger.warning("Failed to load HyPE cache %s: %s", cache_path, e)
        return None


def _save_cached_questions(cache_path: str, questions: dict[str, list[str]]) -> None:
    """Save generated questions to cache file for reuse."""
    import json
    from pathlib import Path
    p = Path(cache_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p, "w") as f:
            json.dump(questions, f, indent=2)
        _hype_logger.info("Saved HyPE cache: %d chunks → %s", len(questions), cache_path)
    except Exception as e:
        _hype_logger.warning("Failed to save HyPE cache %s: %s", cache_path, e)


async def _generate_questions_batch(
    chunks: list[dict[str, Any]],
    n_questions: int,
    model: str,
    max_concurrent: int = 10,
    cache_path: str | None = None,
) -> dict[str, list[str]]:
    """Generate hypothetical questions for a batch of chunks with concurrency control.

    If cache_path is provided, loads cached questions for chunks that were
    previously processed and only generates for new ones.
    """
    # Load cache if available
    cached = _load_cached_questions(cache_path) if cache_path else None
    results: dict[str, list[str]] = dict(cached) if cached else {}

    # Filter to chunks that need generation
    to_generate = [c for c in chunks if c.get("content", "").strip() and c["chunk_id"] not in results]
    if cached:
        _hype_logger.info(
            "HyPE cache hit: %d/%d chunks cached, %d to generate",
            len(chunks) - len(to_generate), len(chunks), len(to_generate),
        )

    if not to_generate:
        return results

    semaphore = asyncio.Semaphore(max_concurrent)
    failed_chunks: list[str] = []

    async def _process(chunk: dict[str, Any]) -> None:
        async with semaphore:
            chunk_id = chunk["chunk_id"]
            questions = await _generate_hypothetical_questions(
                chunk_id, chunk["content"], n_questions, model,
            )
            if questions:
                results[chunk_id] = questions
            else:
                failed_chunks.append(chunk_id)

    tasks = [_process(c) for c in to_generate]
    total = len(tasks)

    # Process in batches with progress logging and periodic cache saves
    batch_size = 50
    for i in range(0, total, batch_size):
        batch = tasks[i:i + batch_size]
        await asyncio.gather(*batch)
        done = min(i + batch_size, total)
        _hype_logger.info("HyPE question generation: %d/%d chunks", done, total)

        # Checkpoint cache every 200 chunks
        if cache_path and done % 200 == 0:
            _save_cached_questions(cache_path, results)

    if failed_chunks:
        _hype_logger.warning("HyPE: %d chunks failed question generation", len(failed_chunks))

    # Final cache save
    if cache_path:
        _save_cached_questions(cache_path, results)

    return results


async def chunk_vdb_build_tool(
    dataset_name: str,
    graphrag_context: GraphRAGContext,
    vdb_collection_name: Optional[str] = None,
    force_rebuild: bool = False,
    embedding_mode: Optional[str] = None,
    hypothetical_questions_per_chunk: Optional[int] = None,
    hypothetical_question_model: Optional[str] = None,
) -> dict:
    """Build a vector database for document chunks.

    Supports HyPE (Hypothetical Prompt Embeddings) — generating questions
    per chunk at build time so query-time matching is question-to-question
    instead of question-to-document. Configurable via ChunkConfig or
    explicit parameters.

    Args:
        dataset_name: Dataset whose chunks to index.
        graphrag_context: The shared GraphRAG context.
        vdb_collection_name: VDB ID. Defaults to '{dataset_name}_chunks'.
        force_rebuild: If True, rebuild even if VDB already exists.
        embedding_mode: Override ChunkConfig.vdb_embedding_mode.
        hypothetical_questions_per_chunk: Override ChunkConfig setting.
        hypothetical_question_model: Override ChunkConfig setting.

    Returns:
        dict with vdb_id, num_chunks_indexed, status, embedding_mode.
    """
    vdb_id = vdb_collection_name or f"{dataset_name}_chunks"

    # Check if already exists
    existing = graphrag_context.get_vdb_instance(vdb_id)
    if existing and not force_rebuild:
        logger.info(f"Chunk VDB '{vdb_id}' already exists, skipping build")
        return {"vdb_id": vdb_id, "num_chunks_indexed": 0, "status": "already_exists"}

    # Resolve config
    chunk_config = getattr(graphrag_context, "chunk_config", None)
    mode = embedding_mode or getattr(chunk_config, "vdb_embedding_mode", "text_only")
    n_questions = hypothetical_questions_per_chunk or getattr(
        chunk_config, "vdb_hypothetical_questions_per_chunk", 3
    )
    q_model = hypothetical_question_model or getattr(
        chunk_config, "vdb_hypothetical_question_model", "gemini/gemini-2.5-flash-lite"
    )

    # Get embedding provider
    embedding_provider = graphrag_context.embedding_provider
    if not embedding_provider:
        raise RuntimeError("No embedding provider available in context")

    # Get chunks from ChunkFactory in GraphRAGContext
    chunk_factory = graphrag_context.chunk_storage_manager
    if chunk_factory is None:
        raise RuntimeError(f"No chunk_storage_manager loaded for dataset '{dataset_name}'")

    # Load chunks from ChunkFactory
    chunks_list = await chunk_factory.get_chunks_for_dataset(dataset_name)
    chunks_dict = {}
    for chunk_id, chunk_obj in chunks_list:
        if hasattr(chunk_obj, "content"):
            chunks_dict[chunk_id] = chunk_obj
        elif isinstance(chunk_obj, str):
            chunks_dict[chunk_id] = chunk_obj
        else:
            chunks_dict[chunk_id] = str(chunk_obj)

    if not chunks_dict:
        raise RuntimeError(f"No chunks found for dataset '{dataset_name}'")

    # Prepare base elements
    base_elements = []
    for chunk_id, chunk in chunks_dict.items():
        if hasattr(chunk, "content"):
            content = chunk.content
            doc_id = getattr(chunk, "doc_id", "")
            title = getattr(chunk, "title", "")
        elif isinstance(chunk, str):
            content = chunk
            doc_id = ""
            title = ""
        else:
            content = str(chunk)
            doc_id = ""
            title = ""

        if not content or not content.strip():
            continue

        base_elements.append({
            "id": str(chunk_id),
            "content": content,
            "chunk_id": str(chunk_id),
            "doc_id": doc_id,
            "title": title,
        })

    if not base_elements:
        raise RuntimeError("All chunks were empty, nothing to index")

    # Build index elements based on embedding mode
    elements = []
    n_questions_generated = 0

    if mode == "text_only":
        elements = base_elements
        logger.info(f"Building chunk VDB '{vdb_id}' with {len(elements)} chunks (text_only)")
    else:
        # Generate hypothetical questions for HyPE
        logger.info(
            f"Generating hypothetical questions for {len(base_elements)} chunks "
            f"(mode={mode}, n_questions={n_questions}, model={q_model})"
        )
        cache_path = f"storage/vdb/{vdb_id}_hype_questions.json"
        questions_by_chunk = await _generate_questions_batch(
            base_elements, n_questions, q_model,
            cache_path=cache_path,
        )
        n_questions_generated = sum(len(qs) for qs in questions_by_chunk.values())
        logger.info(f"Generated {n_questions_generated} hypothetical questions")

        if mode == "questions_only":
            # Each question becomes a separate element pointing to the parent chunk.
            # original_text stores the source chunk so search can return it.
            for elem in base_elements:
                cid = elem["chunk_id"]
                for i, question in enumerate(questions_by_chunk.get(cid, [])):
                    elements.append({
                        "id": f"{cid}_q{i}",
                        "content": question,
                        "chunk_id": cid,
                        "original_text": elem["content"],
                        "doc_id": elem.get("doc_id", ""),
                        "title": elem.get("title", ""),
                    })
        elif mode == "hybrid":
            # Include both chunk text AND questions
            for elem in base_elements:
                elements.append(elem)  # original chunk text
                cid = elem["chunk_id"]
                for i, question in enumerate(questions_by_chunk.get(cid, [])):
                    elements.append({
                        "id": f"{cid}_q{i}",
                        "content": question,
                        "chunk_id": cid,
                        "original_text": elem["content"],
                        "doc_id": elem.get("doc_id", ""),
                        "title": elem.get("title", ""),
                    })
        else:
            logger.warning(f"Unknown embedding_mode '{mode}', falling back to text_only")
            elements = base_elements

    if not elements:
        raise RuntimeError("No elements to index after HyPE processing")

    logger.info(f"Building chunk VDB '{vdb_id}' with {len(elements)} elements (mode={mode})")

    # Create FAISS index
    vdb_storage_path = f"storage/vdb/{vdb_id}"
    config = create_faiss_index_config(
        persist_path=vdb_storage_path,
        embed_model=embedding_provider,
        name=vdb_id,
    )
    chunk_vdb = FaissIndex(config)

    await chunk_vdb.build_index(
        elements=elements,
        meta_data=["id", "content", "chunk_id", "doc_id", "title", "original_text"],
        force=force_rebuild,
    )

    # Register in context
    graphrag_context.add_vdb_instance(vdb_id, chunk_vdb)
    logger.info(f"Chunk VDB '{vdb_id}' built: {len(elements)} elements indexed")

    return {
        "vdb_id": vdb_id,
        "num_chunks_indexed": len(base_elements),
        "num_elements_indexed": len(elements),
        "embedding_mode": mode,
        "hypothetical_questions_generated": n_questions_generated,
        "status": f"Built with {len(elements)} elements (mode={mode})",
    }
