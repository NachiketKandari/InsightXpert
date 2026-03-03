"""RAG bootstrap trainer -- populates the vector store at application startup.

This module is responsible for seeding the ChromaDB vector store with the
training data the analyst agent needs for few-shot SQL generation.  It
populates three of the four collections:

- **ddl** -- CREATE TABLE statements (from ``training/schema.py`` and live
  DB introspection).
- **docs** -- Business-context documentation (from ``training/documentation.py``).
- **qa_pairs** -- Curated question-to-SQL examples (from ``training/queries.py``).

The fourth collection, **findings**, is *not* populated by the trainer.  It
is reserved for a future anomaly-detection pipeline.

**Deduplication:** All items are inserted via ``upsert`` (keyed by a SHA-256
content hash), so calling ``train_insightxpert`` multiple times is safe and
idempotent -- duplicate content is silently ignored.

**Timing:** Training runs synchronously at startup (called from ``main.py``
or the lifespan handler) before the server begins accepting requests.
"""

from __future__ import annotations

import logging

from insightxpert.db.connector import DatabaseConnector
from insightxpert.rag.base import VectorStoreBackend
from insightxpert.training.documentation import DOCUMENTATION
from insightxpert.training.queries import EXAMPLE_QUERIES
from insightxpert.training.schema import DDL

logger = logging.getLogger("insightxpert.training")


class Trainer:
    """Seeds the RAG vector store with DDL, documentation, and example Q&A pairs."""

    def __init__(self, rag: VectorStoreBackend) -> None:
        self._rag = rag

    def train_from_ddl(self, db: DatabaseConnector) -> int:
        """Introspect the live database and add DDL for every table.

        Uses SQLAlchemy's inspector to discover all tables, then
        reconstructs a ``CREATE TABLE`` statement for each one (including
        columns, NOT NULL constraints, primary keys, and foreign keys).
        Each DDL string is upserted into the ``ddl`` collection so the
        analyst LLM has accurate schema context even if the canonical DDL
        in ``training/schema.py`` drifts from the real database.

        Args:
            db: A connected ``DatabaseConnector`` whose engine is used for
                introspection.

        Returns:
            The number of tables whose DDL was added.
        """
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
            self._rag.add_ddl(ddl, table_name=table, metadata={"dataset_id": "__system__", "org_id": "__system__"})
            count += 1

        return count

    def train_from_dataset(self, dataset_service) -> int:
        """Load training data from the active dataset in the DB.

        Reads DDL, documentation, and example queries from the DatasetService
        and adds them to the RAG store. Returns the number of items added,
        or 0 if no active dataset is found.

        All entries are tagged with ``dataset_id`` and ``org_id`` so that
        RAG retrieval can be scoped to the active dataset.
        """
        active = dataset_service.get_active_dataset()
        if not active:
            logger.debug("No active dataset in DB, skipping DB-based training")
            return 0

        count = 0
        dataset_id = active["id"]
        org_id = active.get("organization_id") or "__system__"
        scope_meta = {"dataset_id": dataset_id, "org_id": org_id}

        # DDL
        ddl = active.get("ddl", "")
        if ddl:
            self._rag.add_ddl(ddl, table_name=active.get("name", ""), metadata=scope_meta)
            count += 1
            logger.debug("Added DDL from dataset '%s'", active["name"])

        # Documentation (build from columns if available, else use stored docs)
        docs = dataset_service.build_documentation_markdown(dataset_id)
        if docs:
            self._rag.add_documentation(docs, {"source": "dataset_db", **scope_meta})
            count += 1
            logger.debug("Added documentation from dataset '%s'", active["name"])

        # Example queries
        queries = dataset_service.get_example_queries(dataset_id)
        for q in queries:
            self._rag.add_qa_pair(
                q["question"], q["sql"],
                {"source": "dataset_db", "sql_valid": True, **scope_meta},
            )
            count += 1
        if queries:
            logger.debug("Added %d example Q&A pairs from dataset '%s'", len(queries), active["name"])

        return count

    def train_insightxpert(self, db: DatabaseConnector | None = None, dataset_service=None) -> int:
        """Bootstrap the RAG store with all InsightXpert training data.

        If a ``dataset_service`` is provided, training data is loaded from the
        DB first. Falls back to hardcoded Python files if the DB returns nothing.

        Args:
            db: Optional database connector for live schema introspection.
            dataset_service: Optional DatasetService for DB-based training.

        Returns:
            Total count of items added.
        """
        count = 0

        # Try DB-based training first
        if dataset_service is not None:
            db_count = self.train_from_dataset(dataset_service)
            if db_count > 0:
                count += db_count
                logger.info("Loaded %d training items from DB dataset", db_count)
                # Still do live introspection if DB connector available
                if db is not None:
                    try:
                        ddl_count = self.train_from_ddl(db)
                        count += ddl_count
                        logger.debug("Introspected %d tables from DB", ddl_count)
                    except Exception as e:
                        logger.warning("DB introspection failed: %s", e)
                logger.info("Training complete: %d items total", count)
                return count

        # Fallback: use hardcoded training files
        # Tagged as __system__ so they are visible to all datasets.
        sys_meta = {"dataset_id": "__system__", "org_id": "__system__"}

        # Step 1: Add the canonical DDL for the transactions table
        self._rag.add_ddl(DDL, table_name="transactions", metadata=sys_meta)
        count += 1
        logger.debug("Added DDL for transactions table")

        # Step 2: Add business documentation
        self._rag.add_documentation(DOCUMENTATION, {"source": "insightxpert_training", **sys_meta})
        count += 1
        logger.debug("Added business documentation")

        # Step 3: Add example Q&A pairs (curated examples are always valid SQL)
        for qa in EXAMPLE_QUERIES:
            self._rag.add_qa_pair(qa["question"], qa["sql"], {"source": "insightxpert_training", "sql_valid": True, **sys_meta})
            count += 1
        logger.debug("Added %d example Q&A pairs", len(EXAMPLE_QUERIES))

        # Step 4: Also introspect DB schema if connected
        if db is not None:
            try:
                ddl_count = self.train_from_ddl(db)
                count += ddl_count
                logger.debug("Introspected %d tables from DB", ddl_count)
            except Exception as e:
                logger.warning("DB introspection failed: %s", e)

        logger.info("Training complete: %d items total", count)
        return count
