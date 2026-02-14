from __future__ import annotations

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine


def get_table_info(engine: Engine, table_name: str) -> dict:
    inspector = sa_inspect(engine)
    columns = inspector.get_columns(table_name)
    pks = inspector.get_pk_constraint(table_name)
    fks = inspector.get_foreign_keys(table_name)
    return {
        "table_name": table_name,
        "columns": [
            {"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)}
            for c in columns
        ],
        "primary_keys": pks.get("constrained_columns", []),
        "foreign_keys": [
            {
                "column": fk["constrained_columns"],
                "references": f"{fk['referred_table']}({', '.join(fk['referred_columns'])})",
            }
            for fk in fks
        ],
    }


def get_schema_ddl(engine: Engine) -> str:
    inspector = sa_inspect(engine)
    tables = inspector.get_table_names()
    ddl_parts: list[str] = []

    for table in tables:
        columns = inspector.get_columns(table)
        pks = inspector.get_pk_constraint(table)
        fks = inspector.get_foreign_keys(table)

        col_defs: list[str] = []
        for col in columns:
            parts = [f"  {col['name']} {col['type']}"]
            if not col.get("nullable", True):
                parts.append("NOT NULL")
            col_defs.append(" ".join(parts))

        pk_cols = pks.get("constrained_columns", [])
        if pk_cols:
            col_defs.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

        for fk in fks:
            src = ", ".join(fk["constrained_columns"])
            ref_table = fk["referred_table"]
            ref_cols = ", ".join(fk["referred_columns"])
            col_defs.append(f"  FOREIGN KEY ({src}) REFERENCES {ref_table}({ref_cols})")

        ddl = f"CREATE TABLE {table} (\n" + ",\n".join(col_defs) + "\n);"
        ddl_parts.append(ddl)

    return "\n\n".join(ddl_parts)
