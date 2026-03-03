"""SQL table extractor and validator for table-level access control.

Provides regex-based utilities to extract table names referenced in SQL
queries and validate them against a whitelist of allowed tables.  Used by
``RunSqlTool`` and ``GetSchemaTool`` to enforce dataset isolation -- ensuring
the LLM agent can only query tables belonging to the active dataset.

No external dependencies beyond the standard library.
"""

from __future__ import annotations

import re

# Matches write operations that should never be allowed through the agent tools.
# The analyst tools are read-only; writes go through dedicated API endpoints.
FORBIDDEN_SQL_RE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH)\b",
    re.IGNORECASE,
)

# Matches CTE alias names: WITH <alias> AS (...)
# Used to exclude CTE aliases from the set of "real" table references.
_CTE_RE = re.compile(
    r"\bWITH\s+(?:RECURSIVE\s+)?(\w+)\s+AS\s*\(",
    re.IGNORECASE,
)

# Matches table references after FROM, JOIN variants, INTO, and UPDATE.
# Captures the table name (possibly quoted with backticks or double quotes).
_TABLE_REF_RE = re.compile(
    r"""
    (?:FROM|JOIN|INTO|UPDATE)          # keyword
    \s+                                # whitespace
    ["`]?(\w+)["`]?                    # table name (optionally quoted)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_tables(sql: str) -> set[str]:
    """Extract table names referenced in a SQL query.

    Handles SELECT, subqueries, CTEs, JOINs, and quoted table names.
    CTE alias names (``WITH x AS (...)``) are excluded from the result
    since they are not real tables.

    Args:
        sql: The SQL query string.

    Returns:
        A set of lowercase table names referenced in the query.
    """
    # Collect CTE aliases to exclude
    cte_aliases = {m.group(1).lower() for m in _CTE_RE.finditer(sql)}

    # Collect all table references
    tables = {m.group(1).lower() for m in _TABLE_REF_RE.finditer(sql)}

    # Remove CTE aliases — they aren't real tables
    tables -= cte_aliases

    return tables


def validate_tables(sql: str, allowed: set[str]) -> str | None:
    """Validate that a SQL query only references allowed tables.

    Args:
        sql: The SQL query string.
        allowed: Set of lowercase table names the query is permitted to access.

    Returns:
        ``None`` if the query is valid (all tables allowed), or an error
        message string describing the violation.
    """
    # Check for write operations first
    if FORBIDDEN_SQL_RE.match(sql):
        return "Write operations (INSERT, UPDATE, DELETE, DROP, etc.) are not allowed."

    referenced = extract_tables(sql)
    if not referenced:
        # No tables detected — could be a simple expression like SELECT 1.
        return None

    allowed_lower = {t.lower() for t in allowed}
    forbidden = referenced - allowed_lower

    if forbidden:
        sorted_forbidden = sorted(forbidden)
        sorted_allowed = sorted(allowed_lower)
        return (
            f"Access denied: query references table(s) {sorted_forbidden} "
            f"which are not in the active dataset. "
            f"Allowed tables: {sorted_allowed}"
        )

    return None
