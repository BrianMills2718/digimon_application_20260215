import asyncio
from typing import List, Any
from Core.Graph.BaseGraph import BaseGraph
from Core.Graph.DelimiterExtraction import DelimiterExtractionMixin
from Core.Common.Logger import logger
from Core.Storage.NetworkXStorage import NetworkXStorage


class RKGraph(DelimiterExtractionMixin, BaseGraph):

    def __init__(self, config, llm, encoder):
        # Create a tokenizer wrapper for BaseGraph compatibility
        from Core.Common.TokenizerWrapper import TokenizerWrapper
        tokenizer = TokenizerWrapper()

        super().__init__(config, llm, tokenizer)  # Pass tokenizer instead of encoder
        self._graph = NetworkXStorage()
        # Keep encoder for potential future use
        self.encoder = encoder

    async def _extract_entity_relationship(self, chunk_key_pair: tuple[str, 'TextChunk']):
        chunk_key, chunk_info = chunk_key_pair
        records = await self._extract_records_from_chunk(chunk_info)
        return await self._build_graph_from_records(records, chunk_key)

    async def _build_graph(self, chunk_list: List[Any]):
        try:
            elements = await asyncio.gather(
                *[self._extract_entity_relationship(chunk) for chunk in chunk_list])
            await self.__graph__(elements)
            return True
        except Exception as e:
            logger.exception(f"Error building graph: {e}")
            return False
        finally:
            logger.info("Constructing graph finished")

    @property
    def entity_metakey(self):
        return "entity_name"
