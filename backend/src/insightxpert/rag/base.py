"""Structural typing protocol for the vector store backend.

Defines the ``VectorStoreBackend`` protocol using Python's ``typing.Protocol``
so that the trainer and other consumers can depend on the interface rather
than the concrete ``VectorStore`` implementation.  This enables easy
substitution in tests (e.g. an in-memory fake) and decouples the training
pipeline from ChromaDB specifics.

The protocol is marked ``@runtime_checkable`` so that ``isinstance()``
checks work at runtime (e.g. for defensive assertions), but the primary
benefit is static type checking -- mypy and pyright will verify that any
object passed where ``VectorStoreBackend`` is expected implements all the
required methods with compatible signatures.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VectorStoreBackend(Protocol):
    """Protocol defining the contract for RAG vector store implementations.

    Any class that implements these methods (with compatible signatures) is
    considered a valid ``VectorStoreBackend`` -- no explicit inheritance
    required (structural subtyping).

    The concrete implementation is ``rag.store.VectorStore`` (ChromaDB-backed).
    Test doubles can implement this protocol with in-memory storage.
    """

    def add_qa_pair(self, question: str, sql: str, metadata: dict | None = None) -> str: ...

    def add_ddl(self, ddl: str, table_name: str = "") -> str: ...

    def add_documentation(self, doc: str, metadata: dict | None = None) -> str: ...

    def add_finding(self, finding: str, metadata: dict | None = None) -> str: ...

    def search_qa(self, question: str, n: int = 5, max_distance: float | None = None, sql_valid_only: bool = False) -> list[dict]: ...

    def search_ddl(self, question: str, n: int = 3) -> list[dict]: ...

    def search_docs(self, question: str, n: int = 3) -> list[dict]: ...

    def search_findings(self, question: str, n: int = 3) -> list[dict]: ...

    def flush_qa_pairs(self) -> int: ...

    def delete_all(self) -> dict[str, int]: ...
