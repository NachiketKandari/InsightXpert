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
            self._rag.add_ddl(ddl, table_name=table)
            count += 1

        return count

    def train_insightxpert(self, db: DatabaseConnector | None = None) -> int:
        """Bootstrap the RAG store with all InsightXpert training data.

        Executes a 4-step loading sequence:

        1. **Static DDL** -- The canonical ``CREATE TABLE transactions``
           statement from ``training/schema.py``.
        2. **Business documentation** -- Column descriptions, business rules,
           and domain context from ``training/documentation.py``.
        3. **Example Q&A pairs** -- Curated question-to-SQL examples from
           ``training/queries.py``, each marked ``sql_valid=True``.
        4. **Live DDL introspection** (optional) -- If a ``db`` connector is
           provided, introspects every table in the real database via
           ``train_from_ddl``.

        All items are upserted, making this method **idempotent** -- it can
        be called on every startup without creating duplicate embeddings.

        Note: The **findings** collection is *not* populated here.  It is
        reserved for a future anomaly-detection feature.

        Args:
            db: Optional database connector.  When provided, live schema
                introspection is performed in addition to static training
                data.

        Returns:
            Total count of items added (including DDL, docs, Q&A pairs, and
            introspected tables).
        """
        count = 0

        # Step 1: Add the canonical DDL for the transactions table
        self._rag.add_ddl(DDL, table_name="transactions")
        count += 1
        logger.debug("Added DDL for transactions table")

        # Step 2: Add business documentation
        self._rag.add_documentation(DOCUMENTATION, {"source": "insightxpert_training"})
        count += 1
        logger.debug("Added business documentation")

        # Step 3: Add example Q&A pairs (curated examples are always valid SQL)
        for qa in EXAMPLE_QUERIES:
            self._rag.add_qa_pair(qa["question"], qa["sql"], {"source": "insightxpert_training", "sql_valid": True})
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
