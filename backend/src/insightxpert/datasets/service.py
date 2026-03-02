"""Dataset service -- CRUD and metadata resolution for managed datasets."""

from __future__ import annotations

import io
import logging
import re
import time

import pandas as pd
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from insightxpert.auth.models import Dataset, DatasetColumn, ExampleQuery, _uuid, _utcnow
from insightxpert.datasets.profiler import profile_dataframe

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
        """Generate a safe SQLite table name from a dataset name."""
        safe = name.lower().replace(" ", "_").replace("-", "_")
        safe = re.sub(r"[^a-z0-9_]", "", safe)
        safe = re.sub(r"_+", "_", safe).strip("_")
        if not safe or safe[0].isdigit():
            safe = "ds_" + safe
        return safe

    @staticmethod
    def _pandas_dtype_to_sqlite(dtype) -> str:
        """Map a pandas dtype to a SQLite column type."""
        name = str(dtype)
        if "int" in name:
            return "INTEGER"
        if "float" in name:
            return "REAL"
        if "bool" in name:
            return "INTEGER"
        if "datetime" in name:
            return "TEXT"
        return "TEXT"

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
        """Create a new dataset by parsing a CSV and loading it into SQLite.

        Returns the created dataset dict with a ``profile`` key containing
        the column-level profiling results.  The dataset's ``documentation``
        field is left empty until the user confirms via ``confirm_dataset``.
        Raises ValueError on parse / validation errors.
        """
        # Parse the CSV
        try:
            df = pd.read_csv(io.BytesIO(csv_content))
        except Exception as exc:
            raise ValueError(f"Failed to parse CSV file '{file_name}': {exc}") from exc

        if df.empty:
            raise ValueError("CSV file is empty — no rows found")

        if len(df.columns) == 0:
            raise ValueError("CSV file has no columns")

        # Generate safe table name and check uniqueness
        table_name = self._sanitize_table_name(name)

        with Session(self._engine) as session:
            existing = session.query(Dataset).filter(Dataset.name == name).first()
            if existing:
                raise ValueError(f"A dataset named '{name}' already exists")

        # Profile the dataframe — gets sanitized column names, inferred types, stats
        profile = profile_dataframe(df)

        # Build col_defs from the profiler output (better type detection than pandas dtype)
        # Also build a lookup for quick access by sanitized name
        profile_by_name: dict[str, dict] = {}
        col_defs: list[tuple[str, str]] = []
        for col_profile in profile["columns"]:
            safe_col = col_profile["name"]
            sqlite_type = col_profile["inferred_type"]
            col_defs.append((safe_col, sqlite_type))
            profile_by_name[safe_col] = col_profile

        # Build rename map (original -> sanitized) using profiler's mapping
        rename_map = {
            col_profile["original_name"]: col_profile["name"]
            for col_profile in profile["columns"]
        }
        df = df.rename(columns=rename_map)

        # Build DDL
        col_ddl_parts = [f"    {cname} {ctype}" for cname, ctype in col_defs]
        ddl = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(col_ddl_parts) + "\n);"

        # Documentation is left empty — will be compiled on confirm
        documentation = ""

        # Create the SQLite table and load data
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
            table_name = self._sanitize_table_name(ds.name)
            if ds.ddl:
                m = re.search(
                    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?',
                    ds.ddl,
                    re.IGNORECASE,
                )
                if m:
                    table_name = m.group(1)

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
            table_name = None
            if ds.ddl:
                m = re.search(
                    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)["`]?',
                    ds.ddl,
                    re.IGNORECASE,
                )
                if m:
                    table_name = m.group(1)

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
