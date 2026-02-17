"""Chunk VDB search operator.

Find chunks semantically similar to a query via vector database (embedding search).
Complements chunk.text_search (TF-IDF) — this uses dense embeddings for semantic similarity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from Core.Common.Logger import logger
from Core.Schema.SlotTypes import ChunkRecord, SlotKind, SlotValue


async def chunk_vdb(
    inputs: Dict[str, SlotValue],
    ctx: Any,  # OperatorContext
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, SlotValue]:
    """
    Inputs:  {"query": SlotValue(QUERY_TEXT)}
    Outputs: {"chunks": SlotValue(CHUNK_SET)}
    Params:  {"top_k": int}
    """
    query = inputs["query"].data
    p = params or {}
    top_k = p.get("top_k", getattr(ctx.config, "top_k", 10))

    if ctx.chunks_vdb is None:
        logger.warning("chunk_vdb: no chunks_vdb available in context. Run chunk_vdb_build first.")
        return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=[], producer="chunk.vdb")}

    # Use low-level retrieval() — returns NodeWithScore objects with .metadata, .text, .score
    # (retrieval_nodes() requires a graph param which chunks don't have)
    results = await ctx.chunks_vdb.retrieval(query, top_k)

    if not results:
        return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=[], producer="chunk.vdb")}

    records = []
    for r in results:
        meta = r.metadata if hasattr(r, "metadata") else {}
        chunk_id = meta.get("chunk_id", meta.get("id", ""))
        text = r.text if hasattr(r, "text") else meta.get("content", "")
        score = r.score if hasattr(r, "score") else None

        records.append(ChunkRecord(
            chunk_id=str(chunk_id),
            text=text,
            score=float(score) if score is not None else None,
            extra={"doc_id": meta.get("doc_id", ""), "title": meta.get("title", "")},
        ))

    logger.info(f"chunk_vdb: found {len(records)} chunks for query '{query[:60]}'")
    return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=records, producer="chunk.vdb")}
