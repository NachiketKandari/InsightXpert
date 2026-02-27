"""ChromaDB-backed vector store for RAG retrieval.

Provides semantic search over four domain-specific collections used by the
analyst and training pipelines.  All writes use ``upsert`` keyed by a
truncated SHA-256 hash of the document content, ensuring idempotent inserts.
"""

from __future__ import annotations

import hashlib
import logging

import chromadb

logger = logging.getLogger("insightxpert.rag")


class VectorStore:
    """Persistent ChromaDB vector store managing four embedding collections.

    Collections:
        - **qa_pairs** -- Question-to-SQL pairs used as few-shot examples.
          Populated by the trainer at startup (curated examples) and by the
          analyst's auto-save after each successful answer.
        - **ddl** -- CREATE TABLE statements.  Populated by the trainer from
          both static DDL and live DB introspection.
        - **docs** -- Business-context documentation strings.  Populated by
          the trainer from ``training/documentation.py``.
        - **findings** -- Reserved for anomaly-detection results.  Currently
          never populated; ``search_findings()`` always returns an empty list.

    Deduplication strategy:
        Every document is assigned an ID derived from ``SHA-256(content)[:16]``.
        Writes use ChromaDB's ``upsert``, so inserting the same content twice
        is a no-op.  This makes the trainer safe to call on every startup.

    Distance metric:
        ChromaDB's default L2 (Euclidean) distance is used.  Lower distance
        values indicate higher semantic similarity.  The analyst pipeline
        typically filters results with ``max_distance <= 1.0``.
    """

    def __init__(self, persist_dir: str = "./chroma_data") -> None:
        """Initialize the ChromaDB client and get-or-create all four collections.

        Args:
            persist_dir: Filesystem path where ChromaDB stores its data.
                Defaults to ``./chroma_data`` relative to the working
                directory.
        """
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._qa = self._client.get_or_create_collection("qa_pairs")
        self._ddl = self._client.get_or_create_collection("ddl")
        self._docs = self._client.get_or_create_collection("docs")
        self._findings = self._client.get_or_create_collection("findings")
        logger.debug(
            "VectorStore ready: qa=%d ddl=%d docs=%d findings=%d",
            self._qa.count(), self._ddl.count(), self._docs.count(), self._findings.count(),
        )

    @staticmethod
    def _make_id(text: str) -> str:
        """Derive a deterministic document ID from content via SHA-256.

        The first 16 hex characters of the hash are used as the ChromaDB
        document ID.  This provides content-addressable deduplication:
        upserting the same text twice produces the same ID and overwrites
        (no-ops) the existing entry.

        Args:
            text: The content string to hash.

        Returns:
            A 16-character hex string suitable for use as a ChromaDB ID.
        """
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def add_qa_pair(self, question: str, sql: str, metadata: dict | None = None) -> str:
        """Add a question-SQL pair to the ``qa_pairs`` collection.

        The document stored for embedding is a combined
        ``"Question: ...\\nSQL: ..."`` string so that semantic search matches
        on both the natural-language question and the SQL structure.

        Args:
            question: The natural-language question.
            sql: The corresponding SQL query.
            metadata: Optional extra metadata (e.g. ``{"sql_valid": True}``).

        Returns:
            The deterministic document ID.
        """
        doc_id = self._make_id(question + sql)
        doc = f"Question: {question}\nSQL: {sql}"
        meta = {"question": question, "sql": sql}
        if metadata:
            meta.update(metadata)
        self._qa.upsert(ids=[doc_id], documents=[doc], metadatas=[meta])
        return doc_id

    def add_ddl(self, ddl: str, table_name: str = "") -> str:
        """Add a DDL statement to the ``ddl`` collection.

        Args:
            ddl: The CREATE TABLE (or similar) DDL string.
            table_name: Optional table name stored as metadata for filtering.

        Returns:
            The deterministic document ID.
        """
        doc_id = self._make_id(ddl)
        meta = {"table_name": table_name} if table_name else None
        self._ddl.upsert(ids=[doc_id], documents=[ddl], metadatas=[meta] if meta else None)
        return doc_id

    def add_documentation(self, doc: str, metadata: dict | None = None) -> str:
        """Add a documentation string to the ``docs`` collection.

        Args:
            doc: The documentation text (business context, column descriptions, etc.).
            metadata: Optional metadata (e.g. ``{"source": "insightxpert_training"}``).

        Returns:
            The deterministic document ID.
        """
        doc_id = self._make_id(doc)
        meta = metadata if metadata else None
        self._docs.upsert(ids=[doc_id], documents=[doc], metadatas=[meta] if meta else None)
        return doc_id

    def add_finding(self, finding: str, metadata: dict | None = None) -> str:
        """Add a finding to the ``findings`` collection.

        Note: This method is currently never called by any code path.  It
        exists as a placeholder for a future anomaly-detection pipeline that
        would store background analysis results.

        Args:
            finding: The finding text.
            metadata: Optional metadata.

        Returns:
            The deterministic document ID.
        """
        doc_id = self._make_id(finding)
        meta = metadata if metadata else None
        self._findings.upsert(ids=[doc_id], documents=[finding], metadatas=[meta] if meta else None)
        return doc_id

    def search_qa(
        self,
        question: str,
        n: int = 5,
        max_distance: float | None = None,
        sql_valid_only: bool = False,
    ) -> list[dict]:
        """Search the ``qa_pairs`` collection for similar past queries.

        Uses ChromaDB's embedding-based similarity search.  Results are
        optionally filtered by metadata (``sql_valid``) and post-filtered
        by maximum L2 distance to discard weak matches.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 5).
            max_distance: If set, discard results with distance > this value.
                The analyst pipeline uses 1.0 as the threshold.
            sql_valid_only: If ``True``, only return Q&A pairs whose metadata
                includes ``sql_valid=True`` (i.e. SQL that was successfully
                executed).

        Returns:
            A list of dicts, each with keys ``"document"``, ``"metadata"``,
            and ``"distance"``, sorted by ascending distance.
        """
        count = self._qa.count()
        if count == 0:
            return []
        where = {"sql_valid": True} if sql_valid_only else None
        results = self._qa.query(
            query_texts=[question],
            n_results=min(n, count),
            where=where,
        )
        items = self._unpack(results)
        if max_distance is not None:
            items = [it for it in items if it["distance"] <= max_distance]
        return items

    def search_ddl(self, question: str, n: int = 3) -> list[dict]:
        """Search the ``ddl`` collection for relevant table schemas.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 3).

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
        """
        count = self._ddl.count()
        if count == 0:
            return []
        results = self._ddl.query(query_texts=[question], n_results=min(n, count))
        return self._unpack(results)

    def search_docs(self, question: str, n: int = 3) -> list[dict]:
        """Search the ``docs`` collection for relevant documentation.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 3).

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
        """
        count = self._docs.count()
        if count == 0:
            return []
        results = self._docs.query(query_texts=[question], n_results=min(n, count))
        return self._unpack(results)

    def search_findings(self, question: str, n: int = 3) -> list[dict]:
        """Search the ``findings`` collection for relevant anomaly findings.

        Note: The findings collection is currently never populated, so this
        method always returns an empty list in practice.  It is wired into
        the analyst pipeline to support a future anomaly-detection feature.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 3).

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
        """
        count = self._findings.count()
        if count == 0:
            return []
        results = self._findings.query(query_texts=[question], n_results=min(n, count))
        return self._unpack(results)

    def flush_qa_pairs(self) -> int:
        """Delete all QA pairs, keeping DDL, docs, and findings intact.

        Drops and re-creates the ``qa_pairs`` collection.  This is used by
        admin endpoints to reset the auto-saved Q&A pairs without losing
        the trainer-seeded DDL and documentation.

        Returns:
            The number of QA pairs that were deleted.
        """
        count = self._qa.count()
        if count == 0:
            return 0
        self._client.delete_collection("qa_pairs")
        self._qa = self._client.get_or_create_collection("qa_pairs")
        logger.info("Flushed %d QA pairs", count)
        return count

    def delete_all(self) -> dict[str, int]:
        """Delete all embeddings from all four collections.

        Drops and re-creates every collection.  Used by admin endpoints for
        a full reset.

        Returns:
            A dict mapping collection name to the count of items deleted.
        """
        counts = {
            "qa_pairs": self._qa.count(),
            "ddl": self._ddl.count(),
            "docs": self._docs.count(),
            "findings": self._findings.count(),
        }
        total = sum(counts.values())
        for name in ("qa_pairs", "ddl", "docs", "findings"):
            self._client.delete_collection(name)
        # Re-create empty collections
        self._qa = self._client.get_or_create_collection("qa_pairs")
        self._ddl = self._client.get_or_create_collection("ddl")
        self._docs = self._client.get_or_create_collection("docs")
        self._findings = self._client.get_or_create_collection("findings")
        logger.info("Deleted all embeddings: %d total (%s)", total, counts)
        return counts

    @staticmethod
    def _unpack(results: dict) -> list[dict]:
        """Flatten ChromaDB's nested query response into a list of dicts.

        ChromaDB returns results in a nested structure::

            {
                "documents": [[doc1, doc2, ...]],
                "metadatas": [[meta1, meta2, ...]],
                "distances": [[dist1, dist2, ...]],
            }

        This helper zips the inner lists into a flat list of::

            [{"document": doc1, "metadata": meta1, "distance": dist1}, ...]

        Args:
            results: The raw ChromaDB query response dict.

        Returns:
            A list of dicts, one per result, with ``"document"``,
            ``"metadata"``, and ``"distance"`` keys.
        """
        items: list[dict] = []
        if not results or not results.get("documents"):
            return items
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            items.append({"document": doc, "metadata": meta, "distance": dist})
        return items
