from insightxpert.rag.base import VectorStoreBackend
from insightxpert.rag.memory import InMemoryVectorStore
from insightxpert.rag.store import ChromaVectorStore, VectorStore

__all__ = [
    "VectorStoreBackend",
    "ChromaVectorStore",
    "VectorStore",
    "InMemoryVectorStore",
]

# Verify implementations satisfy the protocol at import time
assert issubclass(ChromaVectorStore, VectorStoreBackend), "ChromaVectorStore must implement VectorStoreBackend"
assert issubclass(InMemoryVectorStore, VectorStoreBackend), "InMemoryVectorStore must implement VectorStoreBackend"
