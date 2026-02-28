"""Dataset service -- CRUD and metadata resolution for managed datasets."""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from insightxpert.auth.models import Dataset, DatasetColumn, ExampleQuery

logger = logging.getLogger("insightxpert.datasets")

_ACTIVE_DS_TTL = 60.0


class DatasetService:
    """Provides dataset metadata from the DB for the analyst agent and trainer."""

    def __init__(self, engine) -> None:
        self._engine = engine
        self._active_ds_cache: tuple[float, dict | None] | None = None

    def get_active_dataset(self) -> dict | None:
        """Return the currently active dataset as a dict, or None."""
        cached = self._active_ds_cache
        if cached is not None:
            cached_at, result = cached
            if time.time() - cached_at < _ACTIVE_DS_TTL:
                return result

        with Session(self._engine) as session:
            ds = session.query(Dataset).filter(Dataset.is_active.is_(True)).first()
            if ds is None:
                self._active_ds_cache = (time.time(), None)
                return None
            result = {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "ddl": ds.ddl,
                "documentation": ds.documentation,
                "is_active": ds.is_active,
                "organization_id": ds.organization_id,
                "created_at": str(ds.created_at),
                "updated_at": str(ds.updated_at),
            }
            self._active_ds_cache = (time.time(), result)
            return result

    def get_dataset_by_id(self, dataset_id: str) -> dict | None:
        """Return a single dataset by ID."""
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return None
            return {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "ddl": ds.ddl,
                "documentation": ds.documentation,
                "is_active": ds.is_active,
                "organization_id": ds.organization_id,
                "created_at": str(ds.created_at),
                "updated_at": str(ds.updated_at),
            }

    def list_datasets(self) -> list[dict]:
        """Return all datasets."""
        with Session(self._engine) as session:
            rows = session.query(Dataset).order_by(Dataset.created_at).all()
            return [
                {
                    "id": ds.id,
                    "name": ds.name,
                    "description": ds.description,
                    "is_active": ds.is_active,
                    "organization_id": ds.organization_id,
                    "created_at": str(ds.created_at),
                    "updated_at": str(ds.updated_at),
                }
                for ds in rows
            ]

    def get_dataset_ddl(self, dataset_id: str) -> str | None:
        """Return the DDL for a dataset."""
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            return ds.ddl if ds else None

    def get_dataset_documentation(self, dataset_id: str) -> str | None:
        """Return the documentation for a dataset."""
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            return ds.documentation if ds else None

    def get_dataset_columns(self, dataset_id: str) -> list[dict]:
        """Return columns for a dataset, ordered by ordinal_position."""
        with Session(self._engine) as session:
            cols = (
                session.query(DatasetColumn)
                .filter(DatasetColumn.dataset_id == dataset_id)
                .order_by(DatasetColumn.ordinal_position)
                .all()
            )
            return [
                {
                    "id": c.id,
                    "column_name": c.column_name,
                    "column_type": c.column_type,
                    "description": c.description,
                    "domain_values": c.domain_values,
                    "domain_rules": c.domain_rules,
                    "ordinal_position": c.ordinal_position,
                }
                for c in cols
            ]

    def get_example_queries(self, dataset_id: str) -> list[dict]:
        """Return active example queries for a dataset."""
        with Session(self._engine) as session:
            rows = (
                session.query(ExampleQuery)
                .filter(
                    ExampleQuery.dataset_id == dataset_id,
                    ExampleQuery.is_active.is_(True),
                )
                .order_by(ExampleQuery.created_at)
                .all()
            )
            return [
                {
                    "id": q.id,
                    "question": q.question,
                    "sql": q.sql,
                    "category": q.category,
                    "is_active": q.is_active,
                }
                for q in rows
            ]

    def build_documentation_markdown(self, dataset_id: str) -> str:
        """Build documentation markdown from DB columns (same format as documentation.py)."""
        ds_dict = self.get_dataset_by_id(dataset_id)
        if not ds_dict:
            return ""

        columns = self.get_dataset_columns(dataset_id)
        if not columns:
            # Fall back to the stored documentation if no column metadata
            return ds_dict.get("documentation", "")

        lines = [ds_dict.get("documentation", "")]

        # Append column details table
        lines.append("\n## Column Details\n")
        lines.append("| Column | Type | Description |")
        lines.append("|--------|------|-------------|")
        for col in columns:
            desc = col.get("description") or ""
            if col.get("domain_values"):
                desc += f" Values: {col['domain_values']}."
            if col.get("domain_rules"):
                desc += f" {col['domain_rules']}."
            lines.append(f"| {col['column_name']} | {col['column_type']} | {desc} |")

        return "\n".join(lines)

    # --- Mutation methods for admin CRUD ---

    def update_dataset(self, dataset_id: str, **fields) -> dict | None:
        """Update dataset fields (ddl, documentation, description, name)."""
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return None
            for key, value in fields.items():
                if hasattr(ds, key):
                    setattr(ds, key, value)
            session.commit()
            session.refresh(ds)
            return self.get_dataset_by_id(dataset_id)

    def activate_dataset(self, dataset_id: str) -> bool:
        """Set one dataset as active, deactivating all others."""
        self._active_ds_cache = None
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return False
            # Deactivate all
            session.query(Dataset).update({Dataset.is_active: False})
            ds.is_active = True
            session.commit()
            return True

    def add_column(self, dataset_id: str, **fields) -> dict | None:
        """Add a column metadata entry to a dataset."""
        from insightxpert.auth.models import _uuid, _utcnow

        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return None
            col = DatasetColumn(
                id=_uuid(),
                dataset_id=dataset_id,
                column_name=fields.get("column_name", ""),
                column_type=fields.get("column_type", "TEXT"),
                description=fields.get("description"),
                domain_values=fields.get("domain_values"),
                domain_rules=fields.get("domain_rules"),
                ordinal_position=fields.get("ordinal_position", 0),
                created_at=_utcnow(),
            )
            session.add(col)
            session.commit()
            return {
                "id": col.id,
                "column_name": col.column_name,
                "column_type": col.column_type,
                "description": col.description,
                "domain_values": col.domain_values,
                "domain_rules": col.domain_rules,
                "ordinal_position": col.ordinal_position,
            }

    def update_column(self, dataset_id: str, col_id: str, **fields) -> dict | None:
        """Update a column metadata entry.

        Returns None if the column does not exist or does not belong to the
        specified dataset.
        """
        with Session(self._engine) as session:
            col = session.get(DatasetColumn, col_id)
            if not col or col.dataset_id != dataset_id:
                return None
            for key, value in fields.items():
                if hasattr(col, key) and key not in ("id", "dataset_id", "created_at"):
                    setattr(col, key, value)
            session.commit()
            session.refresh(col)
            return {
                "id": col.id,
                "column_name": col.column_name,
                "column_type": col.column_type,
                "description": col.description,
                "domain_values": col.domain_values,
                "domain_rules": col.domain_rules,
                "ordinal_position": col.ordinal_position,
            }

    def add_example_query(self, dataset_id: str, **fields) -> dict | None:
        """Add an example query to a dataset."""
        from insightxpert.auth.models import _uuid, _utcnow

        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return None
            eq = ExampleQuery(
                id=_uuid(),
                dataset_id=dataset_id,
                question=fields.get("question", ""),
                sql=fields.get("sql", ""),
                category=fields.get("category"),
                is_active=True,
                created_at=_utcnow(),
            )
            session.add(eq)
            session.commit()
            return {
                "id": eq.id,
                "question": eq.question,
                "sql": eq.sql,
                "category": eq.category,
                "is_active": eq.is_active,
            }

    def delete_example_query(self, dataset_id: str, query_id: str) -> bool:
        """Delete an example query.

        Returns False if the query does not exist or does not belong to the
        specified dataset.
        """
        with Session(self._engine) as session:
            eq = session.get(ExampleQuery, query_id)
            if not eq or eq.dataset_id != dataset_id:
                return False
            session.delete(eq)
            session.commit()
            return True
