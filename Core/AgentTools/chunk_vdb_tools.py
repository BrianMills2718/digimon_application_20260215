"""Chunk VDB Build Tool — creates a FAISS vector index over document chunks.

Enables semantic (embedding-based) chunk retrieval, complementing the existing
TF-IDF keyword search (chunk.text_search). Inspired by EcphoryRAG's dual
retrieval pattern.
"""

from typing import Optional

from Core.AgentSchema.context import GraphRAGContext
from Core.Index.FaissIndex import FaissIndex
from Core.Common.Logger import logger
from Core.AgentTools.index_config_helper import create_faiss_index_config


async def chunk_vdb_build_tool(
    dataset_name: str,
    graphrag_context: GraphRAGContext,
    vdb_collection_name: Optional[str] = None,
    force_rebuild: bool = False,
) -> dict:
    """Build a vector database for document chunks.

    Args:
        dataset_name: Dataset whose chunks to index.
        graphrag_context: The shared GraphRAG context.
        vdb_collection_name: VDB ID. Defaults to '{dataset_name}_chunks'.
        force_rebuild: If True, rebuild even if VDB already exists.

    Returns:
        dict with vdb_id, num_chunks_indexed, status.
    """
    vdb_id = vdb_collection_name or f"{dataset_name}_chunks"

    # Check if already exists
    existing = graphrag_context.get_vdb_instance(vdb_id)
    if existing and not force_rebuild:
        logger.info(f"Chunk VDB '{vdb_id}' already exists, skipping build")
        return {"vdb_id": vdb_id, "num_chunks_indexed": 0, "status": "already_exists"}

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

    # Prepare elements for FAISS indexing
    elements = []
    for chunk_id, chunk in chunks_dict.items():
        # chunk is a TextChunk or a string
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

        elements.append({
            "id": str(chunk_id),
            "content": content,
            "chunk_id": str(chunk_id),
            "doc_id": doc_id,
            "title": title,
        })

    if not elements:
        raise RuntimeError("All chunks were empty, nothing to index")

    logger.info(f"Building chunk VDB '{vdb_id}' with {len(elements)} chunks")

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
        meta_data=["id", "content", "chunk_id", "doc_id", "title"],
        force=force_rebuild,
    )

    # Register in context
    graphrag_context.add_vdb_instance(vdb_id, chunk_vdb)
    logger.info(f"Chunk VDB '{vdb_id}' built: {len(elements)} chunks indexed")

    return {
        "vdb_id": vdb_id,
        "num_chunks_indexed": len(elements),
        "status": f"Built with {len(elements)} chunks",
    }
