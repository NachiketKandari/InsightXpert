from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from insightxpert.db.connector import DatabaseConnector
from insightxpert.rag.base import VectorStoreBackend

logger = logging.getLogger("insightxpert.training")


class Trainer:
    def __init__(self, rag: VectorStoreBackend) -> None:
        self._rag = rag

    def train_from_ddl(self, db: DatabaseConnector) -> int:
        """Auto-introspect DB and add all DDL to ChromaDB. Returns count of tables added."""
        from insightxpert.db.schema import get_table_info
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(db.engine)
        tables = inspector.get_table_names()
        count = 0

        for table in tables:
            info = get_table_info(db.engine, table)
            col_parts = []
            for col in info["columns"]:
                parts = [f"  {col['name']} {col['type']}"]
                if not col.get("nullable", True):
                    parts.append("NOT NULL")
                col_parts.append(" ".join(parts))

            if info["primary_keys"]:
                col_parts.append(f"  PRIMARY KEY ({', '.join(info['primary_keys'])})")

            for fk in info["foreign_keys"]:
                cols = ", ".join(fk["column"]) if isinstance(fk["column"], list) else fk["column"]
                col_parts.append(f"  FOREIGN KEY ({cols}) REFERENCES {fk['references']}")

            ddl = f"CREATE TABLE {table} (\n" + ",\n".join(col_parts) + "\n);"
            self._rag.add_ddl(ddl, table_name=table)
            count += 1

        return count

    def train_from_file(self, path: str) -> int:
        """Load Q&A pairs or docs from JSON or CSV file. Returns count of items added."""
        p = Path(path)
        count = 0

        if p.suffix == ".json":
            with open(p) as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if "question" in item and "sql" in item:
                        self._rag.add_qa_pair(item["question"], item["sql"], item.get("metadata", {}))
                        count += 1
                    elif "doc" in item or "documentation" in item:
                        doc = item.get("doc") or item.get("documentation", "")
                        self._rag.add_documentation(doc, item.get("metadata", {}))
                        count += 1
                    elif "ddl" in item:
                        self._rag.add_ddl(item["ddl"], item.get("table_name", ""))
                        count += 1

        elif p.suffix == ".csv":
            with open(p) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if "question" in row and "sql" in row:
                        self._rag.add_qa_pair(row["question"], row["sql"])
                        count += 1

        return count

    def train_qa(self, question: str, sql: str, metadata: dict | None = None) -> str:
        return self._rag.add_qa_pair(question, sql, metadata)

    def train_doc(self, doc: str, metadata: dict | None = None) -> str:
        return self._rag.add_documentation(doc, metadata)

    def train_ddl(self, ddl: str, table_name: str = "") -> str:
        return self._rag.add_ddl(ddl, table_name)

    def train_insightxpert(self, db: DatabaseConnector | None = None) -> int:
        """Bootstrap RAG with InsightXpert training data: DDL, documentation, and example Q&A pairs."""
        from insightxpert.training.documentation import DOCUMENTATION
        from insightxpert.training.queries import EXAMPLE_QUERIES
        from insightxpert.training.schema import DDL

        count = 0

        # Add the DDL
        self._rag.add_ddl(DDL, table_name="transactions")
        count += 1
        logger.debug("Added DDL for transactions table")

        # Add business documentation
        self._rag.add_documentation(DOCUMENTATION, {"source": "insightxpert_training"})
        count += 1
        logger.debug("Added business documentation")

        # Add example Q&A pairs
        for qa in EXAMPLE_QUERIES:
            self._rag.add_qa_pair(qa["question"], qa["sql"], {"source": "insightxpert_training"})
            count += 1
        logger.debug("Added %d example Q&A pairs", len(EXAMPLE_QUERIES))

        # Also introspect DB schema if connected
        if db is not None:
            try:
                ddl_count = self.train_from_ddl(db)
                count += ddl_count
                logger.debug("Introspected %d tables from DB", ddl_count)
            except Exception as e:
                logger.warning("DB introspection failed: %s", e)

        logger.info("Training complete: %d items total", count)
        return count
