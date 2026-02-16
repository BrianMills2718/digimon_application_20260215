"""Chunk text search operator (TF-IDF / BM25-style).

Keyword search over raw chunk text. Useful when entity-based retrieval
misses relevant passages — searches the actual document text directly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from Core.Common.Logger import logger
from Core.Index.TFIDFStore import TFIDFIndex
from Core.Schema.SlotTypes import ChunkRecord, SlotKind, SlotValue


async def chunk_text_search(
    inputs: Dict[str, SlotValue],
    ctx: Any,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, SlotValue]:
    """
    Inputs:  {"query": SlotValue(QUERY_TEXT),
              "entities": SlotValue(ENTITY_SET, optional) — pre-filter by entity association}
    Outputs: {"chunks": SlotValue(CHUNK_SET)}
    Params:  {"top_k": int}
    """
    query = inputs["query"].data
    p = params or {}
    top_k = p.get("top_k", getattr(ctx.config, "top_k", 10))

    try:
        # Collect all chunk texts from doc_chunks
        if ctx.doc_chunks is None:
            logger.warning("chunk_text_search: no doc_chunks available")
            return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=[], producer="chunk.text_search")}

        # If entity filter provided, narrow search space
        entity_filter = inputs.get("entities")
        if entity_filter and entity_filter.data:
            from Core.Common.Constants import GRAPH_FIELD_SEP
            from Core.Common.Utils import split_string_by_multi_markers

            # Collect chunk IDs from entity source_ids
            chunk_ids = set()
            for entity in entity_filter.data:
                source_ids = split_string_by_multi_markers(
                    entity.source_id, [GRAPH_FIELD_SEP]
                )
                chunk_ids.update(cid for cid in source_ids if cid)

            # Fetch chunk texts
            chunk_id_list = list(chunk_ids)
            chunk_texts = []
            valid_ids = []
            for cid in chunk_id_list:
                data = await ctx.doc_chunks.get_data_by_key(cid)
                if data:
                    valid_ids.append(cid)
                    chunk_texts.append(data)
        else:
            # Get all chunks — iterate through the chunk store
            chunks_dict = ctx.doc_chunks._chunks if hasattr(ctx.doc_chunks, "_chunks") else {}
            valid_ids = list(chunks_dict.keys())
            chunk_texts = list(chunks_dict.values())

        if not chunk_texts:
            logger.warning("chunk_text_search: no chunks to search")
            return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=[], producer="chunk.text_search")}

        # Build TF-IDF index and query
        index = TFIDFIndex()
        index._build_index_from_list(chunk_texts)
        result_indices = index.query(query_str=query, top_k=top_k)

        # Also get cosine similarity scores for ranking
        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = index.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, index.tfidf_matrix).flatten()

        records = []
        for idx in result_indices:
            idx = int(idx)
            records.append(ChunkRecord(
                chunk_id=valid_ids[idx],
                text=chunk_texts[idx],
                score=float(scores[idx]),
                extra={"tfidf_rank": len(records)},
            ))

        logger.info(f"chunk_text_search: found {len(records)} chunks for query '{query[:60]}'")
        return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=records, producer="chunk.text_search")}

    except Exception as e:
        logger.exception(f"chunk_text_search failed: {e}")
        return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=[], producer="chunk.text_search")}
