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
    """Persistent ChromaDB vector store managing five embedding collections.

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
        - **column_metadata** -- Per-column semantic embeddings.  Populated
          when a wide dataset (>20 columns) is confirmed.  Used to prune the
          DDL injected into the analyst prompt to only the columns relevant
          to the user's question.

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
        self._columns = self._client.get_or_create_collection("column_metadata")
        logger.debug(
            "VectorStore ready: qa=%d ddl=%d docs=%d findings=%d columns=%d",
            self._qa.count(), self._ddl.count(), self._docs.count(),
            self._findings.count(), self._columns.count(),
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

    def add_ddl(self, ddl: str, table_name: str = "", metadata: dict | None = None) -> str:
        """Add a DDL statement to the ``ddl`` collection.

        Args:
            ddl: The CREATE TABLE (or similar) DDL string.
            table_name: Optional table name stored as metadata for filtering.
            metadata: Optional extra metadata (e.g. ``{"dataset_id": "..."}``).

        Returns:
            The deterministic document ID.
        """
        doc_id = self._make_id(ddl)
        meta: dict = {}
        if table_name:
            meta["table_name"] = table_name
        if metadata:
            meta.update(metadata)
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

    @staticmethod
    def _build_scope_filter(
        dataset_id: str | None = None,
        org_id: str | None = None,
    ) -> dict | None:
        """Build a ChromaDB ``where`` filter that scopes results to a dataset.

        Returns entries that match the active ``dataset_id`` OR are tagged
        as system entries (``dataset_id == "__system__"``).  When no
        ``dataset_id`` is provided, returns ``None`` (no filtering).
        """
        if not dataset_id:
            return None
        return {"$or": [{"dataset_id": dataset_id}, {"dataset_id": "__system__"}]}

    @staticmethod
    def _merge_where(base: dict | None, extra: dict | None) -> dict | None:
        """Merge two ChromaDB ``where`` clauses with ``$and``."""
        if base and extra:
            return {"$and": [base, extra]}
        return base or extra

    def search_qa(
        self,
        question: str,
        n: int = 3,
        max_distance: float | None = None,
        sql_valid_only: bool = False,
        dataset_id: str | None = None,
        org_id: str | None = None,
    ) -> list[dict]:
        """Search the ``qa_pairs`` collection for similar past queries.

        When ``dataset_id`` is provided, results are scoped to entries
        matching that dataset or tagged as ``"__system__"`` entries.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 3).
            max_distance: If set, discard results with distance > this value.
            sql_valid_only: If ``True``, only return validated Q&A pairs.
            dataset_id: If set, scope results to this dataset + system entries.
            org_id: Reserved for future org-level scoping.

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
        """
        valid_filter = {"sql_valid": True} if sql_valid_only else None
        scope_filter = self._build_scope_filter(dataset_id, org_id)
        where = self._merge_where(valid_filter, scope_filter)

        results = self._qa.query(
            query_texts=[question],
            n_results=n,
            where=where,
        )
        items = self._unpack(results)
        if max_distance is not None:
            items = [it for it in items if it["distance"] <= max_distance]
        return items

    def search_ddl(
        self,
        question: str,
        n: int = 3,
        dataset_id: str | None = None,
        org_id: str | None = None,
    ) -> list[dict]:
        """Search the ``ddl`` collection for relevant table schemas.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 3).
            dataset_id: If set, scope results to this dataset + system entries.
            org_id: Reserved for future org-level scoping.

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
        """
        where = self._build_scope_filter(dataset_id, org_id)
        results = self._ddl.query(query_texts=[question], n_results=n, where=where)
        return self._unpack(results)

    def search_docs(
        self,
        question: str,
        n: int = 3,
        dataset_id: str | None = None,
        org_id: str | None = None,
    ) -> list[dict]:
        """Search the ``docs`` collection for relevant documentation.

        Args:
            question: The natural-language question to search for.
            n: Maximum number of results to return (default 3).
            dataset_id: If set, scope results to this dataset + system entries.
            org_id: Reserved for future org-level scoping.

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
        """
        where = self._build_scope_filter(dataset_id, org_id)
        results = self._docs.query(query_texts=[question], n_results=n, where=where)
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
        results = self._findings.query(query_texts=[question], n_results=n)
        return self._unpack(results)

    def add_column(
        self,
        table_name: str,
        column_name: str,
        description: str,
        metadata: dict | None = None,
    ) -> str:
        """Embed a single column's description into the ``column_metadata`` collection.

        The embedding document is formatted as::

            "{table}.{column}: {description}"

        so that semantic search can match on both the column name and its
        human-readable meaning.

        Args:
            table_name: The table the column belongs to.
            column_name: The column name (sanitized).
            description: Human-readable description (user-provided or auto-generated).
                If empty, the column name is used as the embedding text.
            metadata: Optional extra metadata.  ``table_name``, ``column_name``,
                and ``description`` are always stored automatically.

        Returns:
            The deterministic document ID.
        """
        text = description.strip() if description.strip() else column_name
        doc = f"{table_name}.{column_name}: {text}"
        doc_id = self._make_id(doc)
        meta: dict = {
            "table_name": table_name,
            "column_name": column_name,
            "description": description,
        }
        if metadata:
            meta.update(metadata)
        self._columns.upsert(ids=[doc_id], documents=[doc], metadatas=[meta])
        return doc_id

    def search_columns(
        self,
        question: str,
        n: int = 25,
        dataset_id: str | None = None,
        max_distance: float | None = None,
    ) -> list[dict]:
        """Search the ``column_metadata`` collection for semantically relevant columns.

        Args:
            question: The natural-language question to search against.
            n: Maximum number of columns to return (default 25).
            dataset_id: If set, restrict results to columns tagged with this
                dataset ID.  Returns columns from all datasets if ``None``.
            max_distance: If set, discard results with distance > this value.

        Returns:
            A list of dicts with ``"document"``, ``"metadata"``, ``"distance"``.
            Each ``metadata`` dict contains at least ``table_name``,
            ``column_name``, and ``description``.
        """
        where: dict | None = {"dataset_id": dataset_id} if dataset_id else None
        results = self._columns.query(
            query_texts=[question],
            n_results=min(n, self._columns.count() or 1),
            where=where,
        )
        items = self._unpack(results)
        if max_distance is not None:
            items = [it for it in items if it["distance"] <= max_distance]
        return items

    def delete_columns_for_dataset(self, dataset_id: str) -> int:
        """Delete all column embeddings for a specific dataset.

        Used when a dataset is re-confirmed or deleted, to avoid stale
        column embeddings influencing future queries.

        Args:
            dataset_id: The dataset whose columns should be removed.

        Returns:
            The number of column documents deleted.
        """
        existing = self._columns.get(where={"dataset_id": dataset_id})
        ids = existing.get("ids", [])
        if ids:
            self._columns.delete(ids=ids)
            logger.info("Deleted %d column embeddings for dataset %s", len(ids), dataset_id)
        return len(ids)

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
            "column_metadata": self._columns.count(),
        }
        total = sum(counts.values())
        for name in ("qa_pairs", "ddl", "docs", "findings", "column_metadata"):
            self._client.delete_collection(name)
        # Re-create empty collections
        self._qa = self._client.get_or_create_collection("qa_pairs")
        self._ddl = self._client.get_or_create_collection("ddl")
        self._docs = self._client.get_or_create_collection("docs")
        self._findings = self._client.get_or_create_collection("findings")
        self._columns = self._client.get_or_create_collection("column_metadata")
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
