"""Compute key dataset statistics from the transactions table and store in dataset_stats.

This module is idempotent: if dataset_stats already contains rows it exits immediately
(the transactions table is static and never changes at runtime).

Usage:
    from insightxpert.db.stats_computer import compute_and_store_stats
    n = compute_and_store_stats(engine)   # returns number of rows written, 0 if skipped
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger("insightxpert.stats_computer")

_SQL_QUERIES: dict[str, str] = {
    "overall": """
        SELECT
            COUNT(*)                                                          AS txn_count,
            MIN(DATE(timestamp))                                              AS date_min,
            MAX(DATE(timestamp))                                              AS date_max,
            AVG(amount_inr)                                                   AS avg_amount,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct,
            ROUND(100.0 * SUM(fraud_flag) / COUNT(*), 4)                     AS fraud_rate_pct,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            SUM(fraud_flag)                                                   AS fraud_count
        FROM transactions
    """,
    "transaction_type": """
        SELECT
            transaction_type                                                  AS dimension,
            COUNT(*)                                                          AS txn_count,
            AVG(amount_inr)                                                   AS avg_amount_inr,
            SUM(amount_inr)                                                   AS total_volume_inr,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct,
            SUM(fraud_flag)                                                   AS fraud_count,
            ROUND(100.0 * SUM(fraud_flag) / COUNT(*), 4)                     AS fraud_rate_pct
        FROM transactions
        GROUP BY transaction_type
        ORDER BY txn_count DESC
    """,
    "merchant_category": """
        SELECT
            merchant_category                                                 AS dimension,
            COUNT(*)                                                          AS txn_count,
            AVG(amount_inr)                                                   AS avg_amount_inr,
            SUM(amount_inr)                                                   AS total_volume_inr,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct,
            SUM(fraud_flag)                                                   AS fraud_count,
            ROUND(100.0 * SUM(fraud_flag) / COUNT(*), 4)                     AS fraud_rate_pct
        FROM transactions
        GROUP BY merchant_category
        ORDER BY txn_count DESC
    """,
    "bank": """
        SELECT
            sender_bank                                                       AS dimension,
            COUNT(*)                                                          AS txn_count,
            AVG(amount_inr)                                                   AS avg_amount_inr,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct,
            SUM(fraud_flag)                                                   AS fraud_count,
            ROUND(100.0 * SUM(fraud_flag) / COUNT(*), 4)                     AS fraud_rate_pct
        FROM transactions
        GROUP BY sender_bank
        ORDER BY txn_count DESC
    """,
    "state": """
        SELECT
            sender_state                                                      AS dimension,
            COUNT(*)                                                          AS txn_count,
            AVG(amount_inr)                                                   AS avg_amount_inr,
            SUM(amount_inr)                                                   AS total_volume_inr,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct,
            SUM(fraud_flag)                                                   AS fraud_count,
            ROUND(100.0 * SUM(fraud_flag) / COUNT(*), 4)                     AS fraud_rate_pct
        FROM transactions
        GROUP BY sender_state
        ORDER BY txn_count DESC
    """,
    "age_group": """
        SELECT
            sender_age_group                                                  AS dimension,
            COUNT(*)                                                          AS txn_count,
            AVG(amount_inr)                                                   AS avg_amount_inr,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct
        FROM transactions
        GROUP BY sender_age_group
        ORDER BY sender_age_group
    """,
    "device_type": """
        SELECT
            device_type                                                       AS dimension,
            COUNT(*)                                                          AS txn_count,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct,
            SUM(fraud_flag)                                                   AS fraud_count,
            ROUND(100.0 * SUM(fraud_flag) / COUNT(*), 4)                     AS fraud_rate_pct
        FROM transactions
        GROUP BY device_type
        ORDER BY txn_count DESC
    """,
    "network_type": """
        SELECT
            network_type                                                      AS dimension,
            COUNT(*)                                                          AS txn_count,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            ROUND(100.0 * SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 4) AS failure_rate_pct
        FROM transactions
        GROUP BY network_type
        ORDER BY txn_count DESC
    """,
    "monthly": """
        SELECT
            STRFTIME('%Y-%m', timestamp)                                      AS dimension,
            COUNT(*)                                                          AS txn_count,
            AVG(amount_inr)                                                   AS avg_amount_inr,
            SUM(amount_inr)                                                   AS total_volume_inr,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            SUM(fraud_flag)                                                   AS fraud_count
        FROM transactions
        GROUP BY STRFTIME('%Y-%m', timestamp)
        ORDER BY dimension
    """,
    "hourly": """
        SELECT
            CAST(hour_of_day AS TEXT)                                         AS dimension,
            COUNT(*)                                                          AS txn_count,
            SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END)   AS failure_count,
            SUM(fraud_flag)                                                   AS fraud_count
        FROM transactions
        GROUP BY hour_of_day
        ORDER BY hour_of_day
    """,
}

# Metrics that should be stored as string_value instead of value
_STRING_METRICS = {"date_min", "date_max", "dimension"}


def _upsert_rows(session: Session, group: str, rows: list[dict[str, Any]]) -> int:
    """Insert stat rows for a group. Returns number of rows inserted."""
    from insightxpert.auth.models import DatasetStat

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        dimension = str(row.get("dimension")) if row.get("dimension") is not None else None
        for metric, raw_val in row.items():
            if metric == "dimension":
                continue
            if metric in _STRING_METRICS:
                str_val = str(raw_val) if raw_val is not None else None
                num_val = None
            elif isinstance(raw_val, (int, float)):
                num_val = float(raw_val)
                str_val = None
            elif raw_val is None:
                num_val = None
                str_val = None
            else:
                num_val = None
                str_val = str(raw_val)

            session.add(DatasetStat(
                stat_group=group,
                dimension=dimension,
                metric=metric,
                value=num_val,
                string_value=str_val,
                updated_at=now,
            ))
            count += 1
    return count


def compute_and_store_stats(engine: Engine) -> int:
    """Compute all key stats from the transactions table and store them in dataset_stats.

    Idempotent: exits immediately (returns 0) if dataset_stats already has rows.
    Returns the number of rows written on a fresh computation.
    """
    with engine.connect() as read_conn:
        with Session(engine) as write_session:
            # Check if rows already exist — skip if so (static dataset)
            from insightxpert.auth.models import DatasetStat
            existing = write_session.query(DatasetStat).first()
            if existing is not None:
                logger.debug("dataset_stats already populated, skipping computation")
                return 0

            total_written = 0

            for group, sql in _SQL_QUERIES.items():
                try:
                    result = read_conn.execute(text(sql.strip()))
                    columns = list(result.keys())
                    rows = [dict(zip(columns, row)) for row in result.fetchall()]

                    # For "overall" group there's no "dimension" column — use None
                    if group == "overall":
                        if rows:
                            n = _upsert_rows(write_session, group, rows)
                            total_written += n
                    else:
                        n = _upsert_rows(write_session, group, rows)
                        total_written += n

                    logger.debug("Computed stats for group '%s': %d source rows", group, len(rows))

                except Exception as e:
                    logger.warning("Failed to compute stats for group '%s': %s", group, e)

            write_session.commit()
            logger.info("dataset_stats populated: %d rows written across %d groups", total_written, len(_SQL_QUERIES))
            return total_written
