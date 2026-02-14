from __future__ import annotations

import hashlib
import logging

import chromadb

logger = logging.getLogger("insightxpert.rag")


class ChromaVectorStore:
    def __init__(self, persist_dir: str = "./chroma_data") -> None:
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
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def add_qa_pair(self, question: str, sql: str, metadata: dict | None = None) -> str:
        doc_id = self._make_id(question + sql)
        doc = f"Question: {question}\nSQL: {sql}"
        meta = {"question": question, "sql": sql}
        if metadata:
            meta.update(metadata)
        self._qa.upsert(ids=[doc_id], documents=[doc], metadatas=[meta])
        return doc_id

    def add_ddl(self, ddl: str, table_name: str = "") -> str:
        doc_id = self._make_id(ddl)
        meta = {"table_name": table_name} if table_name else None
        self._ddl.upsert(ids=[doc_id], documents=[ddl], metadatas=[meta] if meta else None)
        return doc_id

    def add_documentation(self, doc: str, metadata: dict | None = None) -> str:
        doc_id = self._make_id(doc)
        meta = metadata if metadata else None
        self._docs.upsert(ids=[doc_id], documents=[doc], metadatas=[meta] if meta else None)
        return doc_id

    def add_finding(self, finding: str, metadata: dict | None = None) -> str:
        doc_id = self._make_id(finding)
        meta = metadata if metadata else None
        self._findings.upsert(ids=[doc_id], documents=[finding], metadatas=[meta] if meta else None)
        return doc_id

    def search_qa(self, question: str, n: int = 5) -> list[dict]:
        if self._qa.count() == 0:
            return []
        results = self._qa.query(query_texts=[question], n_results=min(n, self._qa.count()))
        return self._unpack(results)

    def search_ddl(self, question: str, n: int = 3) -> list[dict]:
        if self._ddl.count() == 0:
            return []
        results = self._ddl.query(query_texts=[question], n_results=min(n, self._ddl.count()))
        return self._unpack(results)

    def search_docs(self, question: str, n: int = 3) -> list[dict]:
        if self._docs.count() == 0:
            return []
        results = self._docs.query(query_texts=[question], n_results=min(n, self._docs.count()))
        return self._unpack(results)

    def search_findings(self, question: str, n: int = 3) -> list[dict]:
        if self._findings.count() == 0:
            return []
        results = self._findings.query(query_texts=[question], n_results=min(n, self._findings.count()))
        return self._unpack(results)

    def delete_all(self) -> dict[str, int]:
        """Delete all embeddings from all collections. Returns count of deleted items per collection."""
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


# Backward-compat alias
VectorStore = ChromaVectorStore
