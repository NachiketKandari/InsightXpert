from __future__ import annotations

import hashlib
from difflib import SequenceMatcher


class InMemoryVectorStore:
    """In-memory vector store for testing. Uses difflib for similarity."""

    def __init__(self) -> None:
        self._qa: dict[str, dict] = {}
        self._ddl: dict[str, dict] = {}
        self._docs: dict[str, dict] = {}
        self._findings: dict[str, dict] = {}

    @staticmethod
    def _make_id(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _search(self, store: dict[str, dict], query: str, n: int) -> list[dict]:
        scored = []
        for item in store.values():
            sim = self._similarity(query, item["document"])
            scored.append((sim, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"document": item["document"], "metadata": item["metadata"], "distance": round(1 - sim, 6)}
            for sim, item in scored[:n]
        ]

    def add_qa_pair(self, question: str, sql: str, metadata: dict | None = None) -> str:
        doc_id = self._make_id(question + sql)
        doc = f"Question: {question}\nSQL: {sql}"
        meta = {"question": question, "sql": sql}
        if metadata:
            meta.update(metadata)
        self._qa[doc_id] = {"document": doc, "metadata": meta}
        return doc_id

    def add_ddl(self, ddl: str, table_name: str = "") -> str:
        doc_id = self._make_id(ddl)
        meta = {"table_name": table_name} if table_name else {}
        self._ddl[doc_id] = {"document": ddl, "metadata": meta}
        return doc_id

    def add_documentation(self, doc: str, metadata: dict | None = None) -> str:
        doc_id = self._make_id(doc)
        self._docs[doc_id] = {"document": doc, "metadata": metadata or {}}
        return doc_id

    def add_finding(self, finding: str, metadata: dict | None = None) -> str:
        doc_id = self._make_id(finding)
        self._findings[doc_id] = {"document": finding, "metadata": metadata or {}}
        return doc_id

    def search_qa(self, question: str, n: int = 5) -> list[dict]:
        return self._search(self._qa, question, n)

    def search_ddl(self, question: str, n: int = 3) -> list[dict]:
        return self._search(self._ddl, question, n)

    def search_docs(self, question: str, n: int = 3) -> list[dict]:
        return self._search(self._docs, question, n)

    def search_findings(self, question: str, n: int = 3) -> list[dict]:
        return self._search(self._findings, question, n)

    def delete_all(self) -> dict[str, int]:
        counts = {
            "qa_pairs": len(self._qa),
            "ddl": len(self._ddl),
            "docs": len(self._docs),
            "findings": len(self._findings),
        }
        self._qa.clear()
        self._ddl.clear()
        self._docs.clear()
        self._findings.clear()
        return counts
