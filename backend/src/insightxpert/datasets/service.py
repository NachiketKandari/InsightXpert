"""Dataset service -- CRUD and metadata resolution for managed datasets."""

from __future__ import annotations

import io
import logging
import re
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from insightxpert.auth.models import Dataset, DatasetColumn, ExampleQuery, _uuid, _utcnow
from insightxpert.datasets.profiler import infer_schema, profile_dataframe

logger = logging.getLogger("insightxpert.datasets")

_ACTIVE_DS_TTL = 60.0

# System / internal tables that must never be overwritten by user uploads.
RESERVED_TABLE_NAMES: set[str] = {
    "transactions",
    "users",
    "sessions",
    "datasets",
    "dataset_columns",
    "example_queries",
    "conversations",
    "conversation_messages",
    "feedback",
    "_sync_deletes",
    "automations",
    "automation_triggers",
    "trigger_templates",
    "prompt_templates",
    "organizations",
    "dataset_stats",
}


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
                "created_by": ds.created_by,
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
                "table_name": self._extract_table_name(ds.ddl),
                "organization_id": ds.organization_id,
                "created_by": ds.created_by,
                "r2_key": ds.r2_key,
                "created_at": str(ds.created_at),
                "updated_at": str(ds.updated_at),
            }

    def list_datasets(
        self,
        *,
        user_id: str | None = None,
        is_super_admin: bool = False,
    ) -> list[dict]:
        """Return datasets visible to the caller.

        Visibility rules for user-uploaded datasets (``created_by IS NOT NULL``):
        - Super admins see everything.
        - Regular users see only their own uploads.
        System datasets (``created_by IS NULL``) are always visible.
        """
        with Session(self._engine) as session:
            q = session.query(Dataset).order_by(Dataset.created_at)

            if not is_super_admin and user_id is not None:
                q = q.filter(
                    or_(
                        Dataset.created_by.is_(None),   # system datasets
                        Dataset.created_by == user_id,   # own uploads
                    )
                )

            return [
                {
                    "id": ds.id,
                    "name": ds.name,
                    "description": ds.description,
                    "is_active": ds.is_active,
                    "table_name": self._extract_table_name(ds.ddl),
                    "organization_id": ds.organization_id,
                    "created_by": ds.created_by,
                    "created_at": str(ds.created_at),
                    "updated_at": str(ds.updated_at),
                }
                for ds in q.all()
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

    @staticmethod
    def _extract_table_name(ddl: str | None) -> str | None:
        """Extract the table name from a CREATE TABLE DDL statement."""
        if not ddl:
            return None
        m = re.search(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?',
            ddl,
            re.IGNORECASE,
        )
        return m.group(1) if m else None

    # --- CSV upload & delete ---

    @staticmethod
    def _sanitize_table_name(name: str) -> str:
        """Generate a safe PostgreSQL table name from a dataset name."""
        safe = name.lower().replace(" ", "_").replace("-", "_")
        safe = re.sub(r"[^a-z0-9_]", "", safe)
        safe = re.sub(r"_+", "_", safe).strip("_")
        if not safe or safe[0].isdigit():
            safe = "ds_" + safe
        return safe

    def _check_reserved_name(self, table_name: str) -> None:
        """Raise ValueError if *table_name* collides with an internal table."""
        if table_name in RESERVED_TABLE_NAMES:
            raise ValueError(
                "This name conflicts with a system table. Please choose a different name."
            )

    # ------------------------------------------------------------------
    # CSV upload — in-memory (legacy, kept for small files / compat)
    # ------------------------------------------------------------------

    def create_dataset_from_csv(
        self,
        *,
        name: str,
        description: str | None,
        created_by: str,
        org_id: str | None,
        csv_content: bytes,
        file_name: str,
    ) -> dict:
        """Create a new dataset by parsing a CSV and loading it into PostgreSQL.

        Returns the created dataset dict with a ``profile`` key containing
        the column-level profiling results.  The dataset's ``documentation``
        field is left empty until the user confirms via ``confirm_dataset``.
        Raises ValueError on parse / validation errors.
        """
        try:
            df = pd.read_csv(io.BytesIO(csv_content))
        except Exception as exc:
            raise ValueError(f"Failed to parse CSV file '{file_name}': {exc}") from exc

        if df.empty:
            raise ValueError("CSV file is empty — no rows found")

        if len(df.columns) == 0:
            raise ValueError("CSV file has no columns")

        # Generate safe table name and check uniqueness + reserved names
        table_name = self._sanitize_table_name(name)
        self._check_reserved_name(table_name)

        with Session(self._engine) as session:
            existing = session.query(Dataset).filter(Dataset.name == name).first()
            if existing:
                raise ValueError(f"A dataset named '{name}' already exists")

        # Profile the dataframe — gets sanitized column names, inferred types, stats
        profile = profile_dataframe(df)

        # Build col_defs from the profiler output (better type detection than pandas dtype)
        profile_by_name: dict[str, dict] = {}
        col_defs: list[tuple[str, str]] = []
        for col_profile in profile["columns"]:
            safe_col = col_profile["name"]
            pg_type = col_profile["inferred_type"]
            col_defs.append((safe_col, pg_type))
            profile_by_name[safe_col] = col_profile

        # Build rename map (original -> sanitized) using profiler's mapping
        rename_map = {
            col_profile["original_name"]: col_profile["name"]
            for col_profile in profile["columns"]
        }
        df = df.rename(columns=rename_map)

        # Build DDL
        col_ddl_parts = [f'    "{cname}" {ctype}' for cname, ctype in col_defs]
        ddl = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(col_ddl_parts) + "\n);"

        documentation = ""

        logger.info(
            "Creating table '%s' with %d columns, loading %d rows from '%s'",
            table_name, len(col_defs), len(df), file_name,
        )
        df.to_sql(table_name, self._engine, if_exists="fail", index=False)
        logger.info("Loaded %d rows into '%s'", len(df), table_name)

        # Persist Dataset + DatasetColumn records
        self._active_ds_cache = None
        dataset_id = _uuid()
        now = _utcnow()

        with Session(self._engine) as session:
            ds = Dataset(
                id=dataset_id,
                name=name,
                description=description,
                ddl=ddl,
                documentation=documentation,
                is_active=False,
                organization_id=org_id,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(ds)

            for idx, (cname, ctype) in enumerate(col_defs):
                col = DatasetColumn(
                    id=_uuid(),
                    dataset_id=dataset_id,
                    column_name=cname,
                    column_type=ctype,
                    description=cname.replace("_", " ").title(),
                    ordinal_position=idx,
                    created_at=now,
                )
                session.add(col)

            session.commit()

        dataset_dict = self.get_dataset_by_id(dataset_id)
        if dataset_dict is None:
            raise RuntimeError("Dataset was just created but not found")
        return {**dataset_dict, "profile": profile}

    # ------------------------------------------------------------------
    # CSV upload — file-based streaming (supports large files up to 500MB)
    # ------------------------------------------------------------------

    def create_dataset_from_csv_file(
        self,
        *,
        name: str,
        description: str | None,
        created_by: str,
        org_id: str | None,
        csv_path: Path,
        file_name: str,
    ) -> dict:
        """Create a new dataset from a CSV file on disk.

        Unlike ``create_dataset_from_csv`` this reads the file in chunks,
        keeping memory usage bounded regardless of file size.

        1. Read a small sample for type inference (schema only).
        2. Create the PostgreSQL table from the inferred schema.
        3. Insert data in 10K-row chunks (each its own transaction).
        4. Profile column stats from the actual loaded table via SQL.
        5. On failure, drop the partial table before re-raising.

        Returns the created dataset dict with a ``profile`` key.
        Raises ``ValueError`` on validation errors.
        """
        # -- Validate name uniqueness & reserved names ----------------------
        table_name = self._sanitize_table_name(name)
        self._check_reserved_name(table_name)

        with Session(self._engine) as session:
            existing = session.query(Dataset).filter(Dataset.name == name).first()
            if existing:
                raise ValueError(f"A dataset named '{name}' already exists")

        # -- 1. Read a small sample for type inference ----------------------
        # Only need ~1000 rows to reliably detect column types; the actual
        # stats (distinct counts, min/max, unique values) are computed from
        # the full loaded table in step 4.
        try:
            sample_df = pd.read_csv(csv_path, nrows=1_000)
        except Exception as exc:
            raise ValueError(f"Failed to parse CSV file '{file_name}': {exc}") from exc

        if sample_df.empty:
            raise ValueError("CSV file is empty — no rows found")
        if len(sample_df.columns) == 0:
            raise ValueError("CSV file has no columns")

        # infer_schema only detects names + types — no stats work
        schema = infer_schema(sample_df)

        col_defs: list[tuple[str, str]] = []
        for col_info in schema:
            col_defs.append((col_info["name"], col_info["inferred_type"]))

        # Build rename map (original CSV header -> sanitized name)
        rename_map = {
            ci["original_name"]: ci["name"] for ci in schema
        }

        # Build DDL
        col_ddl_parts = [f'    "{cname}" {ctype}' for cname, ctype in col_defs]
        ddl = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(col_ddl_parts) + "\n);"

        # Free sample DataFrame memory
        del sample_df

        # -- 2. Create the empty table from DDL ----------------------------
        try:
            with self._engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception as exc:
            raise ValueError(
                f"Failed to create table '{table_name}': {exc}"
            ) from exc
        logger.info("Created table '%s' with %d columns", table_name, len(col_defs))

        # -- 3. Chunked insert (10K rows per batch) ------------------------
        total_rows = 0
        try:
            for chunk in pd.read_csv(csv_path, chunksize=10_000):
                chunk = chunk.rename(columns=rename_map)
                chunk.to_sql(
                    table_name,
                    self._engine,
                    if_exists="append",
                    index=False,
                )
                total_rows += len(chunk)

            logger.info("Loaded %d rows into '%s'", total_rows, table_name)
        except Exception as exc:
            logger.error(
                "Chunked insert failed for '%s' after %d rows: %s",
                table_name, total_rows, exc,
            )
            try:
                with self._engine.begin() as conn:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
                logger.info("Rolled back partial table '%s'", table_name)
            except Exception:
                logger.warning("Failed to drop partial table '%s'", table_name, exc_info=True)
            raise ValueError(
                f"Failed to load CSV data into table '{table_name}': {exc}"
            ) from exc

        # -- 4. Profile from the full loaded table --------------------------
        # Build accurate stats via SQL queries on the actual data.
        profile = {
            "row_count": total_rows,
            "column_count": len(col_defs),
            "columns": [
                {
                    "name": ci["name"],
                    "original_name": ci["original_name"],
                    "inferred_type": ci["inferred_type"],
                    "distinct_count": 0,
                    "null_count": 0,
                    "null_percent": 0.0,
                    "is_unique": False,
                    "cardinality": "low",
                    "unique_values": None,
                    "min": None,
                    "max": None,
                    "mean": None,
                }
                for ci in schema
            ],
        }
        try:
            self._update_profile_from_table(profile, table_name, total_rows)
        except Exception:
            logger.warning("Post-load profiling failed for '%s'; basic stats will be used", table_name, exc_info=True)

        # -- 5. Persist Dataset + DatasetColumn records --------------------
        self._active_ds_cache = None
        dataset_id = _uuid()
        now = _utcnow()

        with Session(self._engine) as session:
            ds = Dataset(
                id=dataset_id,
                name=name,
                description=description,
                ddl=ddl,
                documentation="",
                is_active=False,
                organization_id=org_id,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(ds)

            for idx, (cname, ctype) in enumerate(col_defs):
                col = DatasetColumn(
                    id=_uuid(),
                    dataset_id=dataset_id,
                    column_name=cname,
                    column_type=ctype,
                    description=cname.replace("_", " ").title(),
                    ordinal_position=idx,
                    created_at=now,
                )
                session.add(col)

            session.commit()

        dataset_dict = self.get_dataset_by_id(dataset_id)
        if dataset_dict is None:
            raise RuntimeError("Dataset was just created but not found")
        return {**dataset_dict, "profile": profile}

    # ------------------------------------------------------------------
    # Post-load re-profiling from actual table
    # ------------------------------------------------------------------

    def _update_profile_from_table(
        self, profile: dict, table_name: str, total_rows: int,
    ) -> None:
        """Update profile column stats with actual values from the loaded table.

        Runs one SQL query per column to get accurate distinct counts, nulls,
        uniqueness, and numeric min/max/mean.  The ``unique_values`` list is
        also refreshed for low-cardinality columns (≤50 distinct values).
        """
        from insightxpert.datasets.profiler import _classify_cardinality

        with self._engine.connect() as conn:
            for cp in profile["columns"]:
                col_name = cp["name"]
                quoted = f'"{col_name}"'

                # Distinct count and null count in one pass
                row = conn.execute(text(
                    f"SELECT COUNT(DISTINCT {quoted}) AS dc, "
                    f"SUM(CASE WHEN {quoted} IS NULL THEN 1 ELSE 0 END) AS nc "
                    f'FROM "{table_name}"'
                )).fetchone()

                distinct_count = row[0] if row else cp["distinct_count"]
                null_count = row[1] if row else cp["null_count"]
                non_null_count = total_rows - null_count

                cp["distinct_count"] = distinct_count
                cp["null_count"] = null_count
                cp["null_percent"] = round((null_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
                cp["is_unique"] = (distinct_count == non_null_count) and (non_null_count > 0)
                cp["cardinality"] = _classify_cardinality(distinct_count, total_rows)

                # Numeric stats
                if cp["inferred_type"] in ("INTEGER", "DOUBLE PRECISION"):
                    stats_row = conn.execute(text(
                        f"SELECT MIN({quoted}), MAX({quoted}), AVG({quoted}) "
                        f'FROM "{table_name}" WHERE {quoted} IS NOT NULL'
                    )).fetchone()
                    if stats_row:
                        cp["min"] = stats_row[0]
                        cp["max"] = stats_row[1]
                        cp["mean"] = round(stats_row[2], 2) if stats_row[2] is not None else None

                # Refresh unique_values for low-cardinality columns
                if distinct_count <= 50:
                    uv_rows = conn.execute(text(
                        f"SELECT DISTINCT CAST({quoted} AS TEXT) AS v "
                        f'FROM "{table_name}" WHERE {quoted} IS NOT NULL ORDER BY v'
                    )).fetchall()
                    cp["unique_values"] = [r[0] for r in uv_rows]
                else:
                    cp["unique_values"] = None

    # ------------------------------------------------------------------
    # Orphan cleanup
    # ------------------------------------------------------------------

    def cleanup_stale_unconfirmed(self, max_age_minutes: int = 30) -> int:
        """Delete unconfirmed datasets older than *max_age_minutes*.

        An "unconfirmed" dataset is one where ``is_active = False``,
        ``documentation`` is empty, and ``created_by IS NOT NULL``
        (i.e. user-uploaded, never confirmed).

        Returns the number of cleaned-up datasets.
        """
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        cleaned = 0

        with Session(self._engine) as session:
            stale = (
                session.query(Dataset)
                .filter(
                    Dataset.is_active.is_(False),
                    Dataset.documentation == "",
                    Dataset.created_by.isnot(None),
                    Dataset.created_at < cutoff,
                )
                .all()
            )

            for ds in stale:
                # Drop the data table in a separate transaction (DDL)
                table_name = self._extract_table_name(ds.ddl)
                if table_name and re.fullmatch(r"[a-z0-9_]+", table_name):
                    try:
                        with self._engine.begin() as conn:
                            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
                        logger.info("Orphan cleanup: dropped table '%s'", table_name)
                    except Exception:
                        logger.warning("Orphan cleanup: failed to drop '%s'", table_name, exc_info=True)

                # Delete metadata (DML) in the session
                session.query(DatasetColumn).filter(
                    DatasetColumn.dataset_id == ds.id
                ).delete()
                session.query(ExampleQuery).filter(
                    ExampleQuery.dataset_id == ds.id
                ).delete()
                session.delete(ds)
                cleaned += 1
                logger.info("Orphan cleanup: removed dataset '%s' (id=%s)", ds.name, ds.id)

            if cleaned:
                session.commit()

        return cleaned

    def confirm_dataset(
        self,
        dataset_id: str,
        user_id: str,
        is_admin: bool,
        column_descriptions: dict[str, str],
        profile: dict,
    ) -> dict | None:
        """Finalize a dataset after upload by compiling rich documentation.

        Merges the profiler's column-level stats with user-provided
        descriptions to produce comprehensive documentation for the LLM
        agent.

        Returns the updated dataset dict, or ``None`` if the dataset does
        not exist.  Raises ``PermissionError`` if the user is not the owner
        and not an admin.
        """
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return None

            # Ownership check (same pattern as delete)
            if not is_admin and ds.created_by != user_id:
                raise PermissionError("You can only confirm datasets you created")

            # Build a lookup of profiled columns by name
            profile_cols: dict[str, dict] = {}
            for cp in profile.get("columns", []):
                profile_cols[cp["name"]] = cp

            # Compile documentation markdown --------------------------------
            doc_lines: list[str] = [f"# {ds.name}"]
            if ds.description:
                doc_lines.append(ds.description)
            doc_lines.append("")

            # Extract table name from DDL
            table_name = self._extract_table_name(ds.ddl) or self._sanitize_table_name(ds.name)

            doc_lines.append(f"Table: `{table_name}`")
            doc_lines.append(f"Rows: {profile.get('row_count', 'N/A'):,}")
            doc_lines.append(f"Columns: {profile.get('column_count', 'N/A')}")
            doc_lines.append("")
            doc_lines.append("## Column Details")
            doc_lines.append("")
            doc_lines.append("| Column | Type | Distinct | Description |")
            doc_lines.append("|--------|------|----------|-------------|")

            # Update DatasetColumn records and build documentation rows
            columns = (
                session.query(DatasetColumn)
                .filter(DatasetColumn.dataset_id == dataset_id)
                .order_by(DatasetColumn.ordinal_position)
                .all()
            )

            for col in columns:
                cp = profile_cols.get(col.column_name, {})
                user_desc = column_descriptions.get(col.column_name, "")

                # Build the description cell for the markdown table
                desc_parts: list[str] = []
                if user_desc:
                    desc_parts.append(user_desc)
                elif col.description:
                    desc_parts.append(col.description)

                # Enrich based on profiler stats
                if cp.get("is_unique"):
                    if not user_desc:
                        desc_parts = ["Unique identifier"]
                    # Note uniqueness even if user provided a description
                    elif "unique" not in user_desc.lower():
                        desc_parts.append("(unique)")

                if cp.get("unique_values") is not None:
                    vals = ", ".join(str(v) for v in cp["unique_values"])
                    desc_parts.append(f"Values: {vals}")

                if cp.get("min") is not None and cp.get("max") is not None:
                    range_str = f"Range: {cp['min']} \u2013 {cp['max']}"
                    if cp.get("mean") is not None:
                        range_str += f" (avg: {cp['mean']:.2f})"
                    desc_parts.append(range_str)

                description_cell = ". ".join(desc_parts) if desc_parts else ""

                # Distinct count display
                distinct = cp.get("distinct_count", "")
                if cp.get("is_unique") and distinct:
                    distinct_str = f"{distinct:,} (unique)"
                elif distinct:
                    distinct_str = f"{distinct:,}"
                else:
                    distinct_str = ""

                doc_lines.append(
                    f"| {col.column_name} | {col.column_type} | {distinct_str} | {description_cell} |"
                )

                # Update the DatasetColumn record
                if user_desc:
                    col.description = user_desc
                if cp.get("unique_values") is not None:
                    col.domain_values = ", ".join(str(v) for v in cp["unique_values"])

            documentation = "\n".join(doc_lines)
            ds.documentation = documentation
            ds.updated_at = _utcnow()

            # Auto-activate: deactivate all others, make this one active
            session.query(Dataset).filter(Dataset.id != dataset_id).update(
                {Dataset.is_active: False}
            )
            ds.is_active = True

            session.commit()

        self._active_ds_cache = None
        logger.info("Confirmed dataset %s with %d column descriptions", dataset_id, len(column_descriptions))
        return self.get_dataset_by_id(dataset_id)

    def delete_dataset(
        self,
        dataset_id: str,
        user_id: str,
        is_admin: bool,
    ) -> bool:
        """Delete a dataset, its data table, columns, and example queries.

        Non-admin users can only delete datasets they created.
        Returns True on success, False if not found.
        Raises PermissionError if the user is not the owner and not an admin.
        """
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            if not ds:
                return False

            # Prevent deletion of the seeded default dataset
            if ds.created_by is None:
                raise ValueError(
                    "The default transactions dataset cannot be deleted."
                )

            # Ownership check
            if not is_admin and ds.created_by != user_id:
                raise PermissionError("You can only delete datasets you created")

            was_active = ds.is_active

            # Extract table name from DDL and drop the data table
            table_name = self._extract_table_name(ds.ddl)

            if table_name and re.fullmatch(r"[a-z0-9_]+", table_name):
                try:
                    session.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
                    logger.info("Dropped data table '%s'", table_name)
                except Exception:
                    logger.warning("Failed to drop table '%s'", table_name, exc_info=True)
            elif table_name:
                logger.warning("Refusing to drop table with unsafe name: %r", table_name)

            # Delete related records
            session.query(DatasetColumn).filter(
                DatasetColumn.dataset_id == dataset_id,
            ).delete()
            session.query(ExampleQuery).filter(
                ExampleQuery.dataset_id == dataset_id,
            ).delete()

            session.delete(ds)

            # If we just deleted the active dataset, activate the default one
            if was_active:
                fallback = (
                    session.query(Dataset)
                    .filter(Dataset.created_by.is_(None))
                    .first()
                )
                if fallback:
                    fallback.is_active = True

            session.commit()

        self._active_ds_cache = None
        logger.info("Deleted dataset %s (table=%s)", dataset_id, table_name)
        return True

    def get_dataset_owner(self, dataset_id: str) -> str | None:
        """Return the created_by user ID for a dataset, or None."""
        with Session(self._engine) as session:
            ds = session.get(Dataset, dataset_id)
            return ds.created_by if ds else None
