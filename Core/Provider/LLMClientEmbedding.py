"""LlamaIndex embedding that delegates to llm_client.embed()/aembed().

All calls get logged to io_log (cost, tokens, latency) automatically.
"""

from __future__ import annotations

from llama_index.core.embeddings import BaseEmbedding


class LLMClientEmbedding(BaseEmbedding):
    """LlamaIndex BaseEmbedding backed by llm_client.

    Drop-in replacement for OpenAIEmbedding. Routes through llm_client
    so every call is logged (JSONL + SQLite) with cost/token tracking.
    """

    llm_model: str = "text-embedding-3-small"
    llm_dimensions: int | None = None
    llm_task: str | None = None
    llm_trace_id: str | None = None

    def _get_text_embedding(self, text: str) -> list[float]:
        from llm_client import embed

        result = embed(self.llm_model, text, dimensions=self.llm_dimensions, task=self.llm_task, trace_id=self.llm_trace_id)
        return result.embeddings[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        from llm_client import embed

        result = embed(self.llm_model, texts, dimensions=self.llm_dimensions, task=self.llm_task, trace_id=self.llm_trace_id)
        return result.embeddings

    async def _aget_text_embedding(self, text: str) -> list[float]:
        from llm_client import aembed

        result = await aembed(self.llm_model, text, dimensions=self.llm_dimensions, task=self.llm_task, trace_id=self.llm_trace_id)
        return result.embeddings[0]

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        from llm_client import aembed

        result = await aembed(self.llm_model, texts, dimensions=self.llm_dimensions, task=self.llm_task, trace_id=self.llm_trace_id)
        return result.embeddings

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await self._aget_text_embedding(query)
