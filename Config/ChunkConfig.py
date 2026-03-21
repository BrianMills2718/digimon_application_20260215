from Core.Utils.YamlModel import YamlModel


class ChunkConfig(YamlModel):
    """Configuration for document chunking and chunk VDB indexing."""

    chunk_token_size: int = 1200
    chunk_overlap_token_size: int = 100
    chunk_method: str = "chunking_by_token_size"

    # HyPE (Hypothetical Prompt Embeddings) for chunk VDB
    # At build time, generate questions each chunk answers, embed those.
    # At query time, question-to-question matching bridges vocabulary gaps.
    vdb_embedding_mode: str = "text_only"  # "text_only" | "questions_only" | "hybrid"
    vdb_hypothetical_questions_per_chunk: int = 3
    vdb_hypothetical_question_model: str = "gemini/gemini-2.5-flash-lite"
