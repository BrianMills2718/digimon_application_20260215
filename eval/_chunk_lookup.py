"""ChunkLookup adapter for eval harness.

Wraps a dict of {chunk_id: text} as a key-value store compatible
with OperatorContext.doc_chunks interface.
"""


class ChunkLookup:
    """Wraps a dict as a key-value store for operators."""

    def __init__(self, chunks_dict: dict):
        self._chunks = chunks_dict

    async def get_data_by_key(self, chunk_id: str):
        return self._chunks.get(chunk_id)

    async def get_data_by_indices(self, indices):
        keys = list(self._chunks.keys())
        return [
            self._chunks[keys[i]] if i < len(keys) else None
            for i in indices
        ]
