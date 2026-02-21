"""Chunk text search operator (TF-IDF / BM25-style).

Keyword search over raw chunk text. Useful when entity-based retrieval
misses relevant passages — searches the actual document text directly.
"""

from __future__ import annotations

import re
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
        candidate_k = p.get("candidate_k", max(top_k * 5, 20))
        candidate_k = min(len(chunk_texts), max(top_k, candidate_k))
        result_indices = index.query(query_str=query, top_k=candidate_k)

        # Also get cosine similarity scores for ranking
        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = index.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, index.tfidf_matrix).flatten()

        # Hybrid rerank over TF-IDF candidates:
        # keep lexical relevance while preferring passages that contain
        # high-IDF query terms and contiguous query n-grams.
        query_lower = (query or "").lower().strip()
        query_tokens = re.findall(r"[a-z0-9]+", query_lower)
        query_bigrams = [" ".join(query_tokens[i : i + 2]) for i in range(max(len(query_tokens) - 1, 0))]
        query_trigrams = [" ".join(query_tokens[i : i + 3]) for i in range(max(len(query_tokens) - 2, 0))]
        query_ngrams = [ng for ng in (query_bigrams + query_trigrams) if ng]

        vocab = getattr(index.vectorizer, "vocabulary_", {}) or {}
        idf = getattr(index.vectorizer, "idf_", None)
        avg_idf = 1.0
        if idf is not None and len(idf) > 0:
            avg_idf = float(sum(idf) / len(idf))

        token_weights: dict[str, float] = {}
        for tok in set(query_tokens):
            if idf is not None and tok in vocab:
                token_weights[tok] = float(idf[vocab[tok]])
            else:
                token_weights[tok] = avg_idf
        weight_total = sum(token_weights.values()) or 1.0

        ranked_records: list[tuple[float, float, ChunkRecord]] = []
        for tfidf_rank, idx in enumerate(result_indices):
            idx = int(idx)
            tfidf_score = float(scores[idx])
            text = chunk_texts[idx]
            text_lower = text.lower()
            text_tokens = set(re.findall(r"[a-z0-9]+", text_lower))

            coverage = 0.0
            if token_weights:
                coverage = sum(
                    weight for tok, weight in token_weights.items()
                    if tok in text_tokens
                ) / weight_total

            phrase_hits = 0
            for ng in query_ngrams:
                if ng in text_lower:
                    phrase_hits += 1
            phrase_bonus = min(0.30, 0.06 * phrase_hits)
            exact_bonus = 0.20 if query_lower and query_lower in text_lower else 0.0

            hybrid_score = tfidf_score + (0.45 * coverage) + phrase_bonus + exact_bonus

            ranked_records.append((
                hybrid_score,
                tfidf_score,
                ChunkRecord(
                    chunk_id=valid_ids[idx],
                    text=text,
                    score=hybrid_score,
                    extra={
                        "tfidf_score": tfidf_score,
                        "tfidf_rank": tfidf_rank,
                        "hybrid_score": hybrid_score,
                        "coverage": coverage,
                        "phrase_hits": phrase_hits,
                        "exact_match": bool(exact_bonus),
                    },
                ),
            ))

        ranked_records.sort(key=lambda x: (x[0], x[1]), reverse=True)
        records = [rec for _, _, rec in ranked_records[:top_k]]

        logger.info(f"chunk_text_search: found {len(records)} chunks for query '{query[:60]}'")
        return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=records, producer="chunk.text_search")}

    except Exception as e:
        logger.exception(f"chunk_text_search failed: {e}")
        return {"chunks": SlotValue(kind=SlotKind.CHUNK_SET, data=[], producer="chunk.text_search")}
