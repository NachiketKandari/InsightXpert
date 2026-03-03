"""Pure computational DataFrame profiling module.

Takes a pandas DataFrame and returns a profile dict with column-level
statistics, type inference, cardinality classification, and sample values.
No database or API dependencies.
"""

from __future__ import annotations

import re
import warnings
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# PostgreSQL reserved keywords that cannot be used as unquoted column names.
# This is the subset most likely to appear as CSV column headers.
_RESERVED_KEYWORDS: set[str] = {
    "all", "alter", "and", "any", "array", "as", "asc", "between", "by",
    "case", "cast", "check", "collate", "column", "constraint", "create",
    "cross", "current", "current_date", "current_time", "current_timestamp",
    "current_user", "default", "delete", "desc", "distinct", "do", "drop",
    "else", "end", "except", "exists", "false", "fetch", "filter", "for",
    "foreign", "from", "full", "grant", "group", "having", "if", "ilike",
    "in", "index", "initially", "inner", "insert", "intersect", "into",
    "is", "isnull", "join", "key", "lateral", "leading", "left", "like",
    "limit", "natural", "new", "no", "not", "null", "offset", "old", "on",
    "only", "or", "order", "outer", "over", "overlaps", "partition",
    "placing", "primary", "references", "returning", "right", "row", "rows",
    "select", "session_user", "set", "similar", "some", "symmetric", "table",
    "then", "to", "trailing", "true", "union", "unique", "update", "user",
    "using", "values", "variadic", "verbose", "when", "where", "window",
    "with",
}


def _sanitize_column_name(name: str) -> str:
    """Generate a safe PostgreSQL column name from a raw CSV header."""
    safe = re.sub(r"[^a-z0-9_]", "_", name.strip().lower())
    safe = re.sub(r"_+", "_", safe).strip("_")
    safe = safe or "col"
    # Prefix reserved keywords so they don't clash with PostgreSQL syntax
    if safe in _RESERVED_KEYWORDS:
        safe = f"col_{safe}"
    return safe


_BOOLEAN_PAIRS: list[set[str]] = [
    {"true", "false"},
    {"yes", "no"},
    {"0", "1"},
    {"y", "n"},
    {"t", "f"},
]


def _is_boolean_like(series: pd.Series) -> bool:
    """Return True if a text column has exactly two distinct non-null values
    that match a known boolean pair (case-insensitive)."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    distinct = set(non_null.astype(str).str.strip().str.lower().unique())
    if len(distinct) != 2:
        return False
    return any(distinct == pair for pair in _BOOLEAN_PAIRS)


def _is_datetime_like(series: pd.Series) -> bool:
    """Return True if >=90 % of non-null text values parse as datetimes."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        converted = pd.to_datetime(non_null, errors="coerce")
    success_rate = converted.notna().sum() / len(non_null)
    return success_rate >= 0.9


def _native(value: Any) -> Any:
    """Convert numpy/pandas scalars to native Python types for JSON safety."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    return value


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def _infer_type(series: pd.Series) -> str:
    """Map a pandas Series dtype to a PostgreSQL type string.

    For object/string columns, additionally checks for boolean-like and
    datetime-like patterns.
    """
    dtype = series.dtype

    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "INTEGER"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"

    # Object / string columns: try deeper detection
    if _is_boolean_like(series):
        return "BOOLEAN"
    if _is_datetime_like(series):
        return "TIMESTAMP"

    return "TEXT"


# ---------------------------------------------------------------------------
# Cardinality
# ---------------------------------------------------------------------------

def _classify_cardinality(distinct_count: int, row_count: int) -> str:
    if row_count == 0:
        return "low"
    if distinct_count == row_count:
        return "unique"
    ratio = distinct_count / row_count
    if ratio > 0.5:
        return "high"
    if ratio > 0.05:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def profile_dataframe(df: pd.DataFrame) -> dict:
    """Profile a DataFrame and return column-level statistics.

    Returns a dict with ``row_count``, ``column_count``, and a ``columns``
    list containing per-column metadata including inferred type, nulls,
    cardinality, unique/sample values, and numeric stats.
    """
    row_count: int = len(df)
    column_count: int = len(df.columns)

    columns: list[dict[str, Any]] = []

    for col in df.columns:
        original_name = str(col)
        sanitized_name = _sanitize_column_name(original_name)
        series: pd.Series = df[col]

        inferred_type = _infer_type(series)

        null_count = int(series.isna().sum())
        null_percent = round((null_count / row_count) * 100, 2) if row_count > 0 else 0.0

        non_null = series.dropna()
        distinct_count = int(non_null.nunique())

        # is_unique: every non-null value appears exactly once
        is_unique = (distinct_count == len(non_null)) and (len(non_null) > 0)

        cardinality = _classify_cardinality(distinct_count, row_count)

        # Unique values (sorted, as strings) when cardinality is manageable
        if distinct_count <= 50:
            unique_values = sorted(str(v) for v in non_null.unique())
        else:
            unique_values = None

        # Numeric stats
        col_min = None
        col_max = None
        col_mean = None

        if inferred_type in ("INTEGER", "DOUBLE PRECISION") and not non_null.empty:
            col_min = _native(non_null.min())
            col_max = _native(non_null.max())
            raw_mean = _native(non_null.mean())
            if raw_mean is not None:
                col_mean = round(raw_mean, 2)

        columns.append(
            {
                "name": sanitized_name,
                "original_name": original_name,
                "inferred_type": inferred_type,
                "distinct_count": distinct_count,
                "null_count": null_count,
                "null_percent": null_percent,
                "is_unique": is_unique,
                "cardinality": cardinality,
                "unique_values": unique_values,
                "min": col_min,
                "max": col_max,
                "mean": col_mean,
            }
        )

    return {
        "row_count": row_count,
        "column_count": column_count,
        "columns": columns,
    }


def infer_schema(df: pd.DataFrame) -> list[dict[str, str]]:
    """Infer column names and PostgreSQL types from a DataFrame sample.

    Returns a list of ``{"name": ..., "original_name": ..., "inferred_type": ...}``
    dicts.  No stats are computed — this is meant for a small sample used only
    to determine the table schema before a chunked load.
    """
    result: list[dict[str, str]] = []
    for col in df.columns:
        original_name = str(col)
        sanitized_name = _sanitize_column_name(original_name)
        inferred_type = _infer_type(df[col])
        result.append({
            "name": sanitized_name,
            "original_name": original_name,
            "inferred_type": inferred_type,
        })
    return result
