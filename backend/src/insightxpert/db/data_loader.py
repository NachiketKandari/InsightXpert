"""Universal data loader: CSV/Excel -> any SQLAlchemy-supported database.

Usage:
    python -m insightxpert.db.data_loader --source data.csv --table transactions
    python -m insightxpert.db.data_loader --source data.xlsx --table transactions
    python -m insightxpert.db.data_loader --source data.csv --table transactions --db-url postgresql://...
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("data_loader")

# Column mapping from CSV headers -> DB column names (for transaction data)
COLUMN_MAP = {
    "transaction id": "transaction_id",
    "timestamp": "timestamp",
    "transaction type": "transaction_type",
    "merchant_category": "merchant_category",
    "amount (INR)": "amount_inr",
    "transaction_status": "transaction_status",
    "sender_age_group": "sender_age_group",
    "receiver_age_group": "receiver_age_group",
    "sender_state": "sender_state",
    "sender_bank": "sender_bank",
    "receiver_bank": "receiver_bank",
    "device_type": "device_type",
    "network_type": "network_type",
    "fraud_flag": "fraud_flag",
    "hour_of_day": "hour_of_day",
    "day_of_week": "day_of_week",
    "is_weekend": "is_weekend",
}

# Indexes to create after loading transaction data
TRANSACTION_INDEXES = [
    ("idx_txn_type", "transactions", "transaction_type"),
    ("idx_status", "transactions", "transaction_status"),
    ("idx_merchant", "transactions", "merchant_category"),
    ("idx_sender_bank", "transactions", "sender_bank"),
    ("idx_device", "transactions", "device_type"),
    ("idx_fraud", "transactions", "fraud_flag"),
    ("idx_hour", "transactions", "hour_of_day"),
    ("idx_weekend", "transactions", "is_weekend"),
    ("idx_state", "transactions", "sender_state"),
    ("idx_timestamp", "transactions", "timestamp"),
]


def _read_source(path: Path) -> pd.DataFrame:
    """Read CSV or Excel file into a DataFrame."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Use .csv, .xlsx, or .xls")


def _apply_column_map(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Rename columns using COLUMN_MAP if loading transaction data."""
    if table == "transactions":
        # Normalize CSV headers: lowercase for matching
        csv_cols = {c.strip().lower(): c for c in df.columns}
        rename_map = {}
        for csv_name, db_name in COLUMN_MAP.items():
            if csv_name.lower() in csv_cols:
                rename_map[csv_cols[csv_name.lower()]] = db_name
        if rename_map:
            df = df.rename(columns=rename_map)
            logger.info("Renamed %d columns using transaction column map", len(rename_map))
    return df


def _create_indexes(engine, table: str) -> None:
    """Create indexes for known tables."""
    if table != "transactions":
        return
    with engine.begin() as conn:
        for idx_name, tbl, col in TRANSACTION_INDEXES:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl}({col})"))
                logger.info("Created index %s on %s(%s)", idx_name, tbl, col)
            except Exception:
                logger.debug("Index %s already exists", idx_name)


def load_data(
    source: Path,
    table: str,
    db_url: str,
    if_exists: str = "replace",
    batch_size: int = 10_000,
) -> int:
    """Load data from CSV/Excel into any SQLAlchemy-supported database."""
    start = time.time()

    logger.info("Reading %s...", source)
    df = _read_source(source)
    logger.info("Read %d rows, %d columns", len(df), len(df.columns))

    # Apply column mapping for known tables
    df = _apply_column_map(df, table)

    engine = create_engine(db_url)

    # Load data in batches using pandas to_sql
    logger.info("Loading into table '%s' (if_exists=%s)...", table, if_exists)
    df.to_sql(table, engine, if_exists=if_exists, index=False, chunksize=batch_size)
    logger.info("Loaded %d rows into '%s'", len(df), table)

    # Create indexes
    _create_indexes(engine, table)

    elapsed = time.time() - start
    logger.info("Done in %.1fs", elapsed)

    engine.dispose()
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load CSV/Excel data into any SQLAlchemy-supported database",
    )
    parser.add_argument(
        "--source", required=True, type=Path,
        help="Path to CSV or Excel file",
    )
    parser.add_argument(
        "--table", required=True,
        help="Target table name",
    )
    parser.add_argument(
        "--db-url", default=None,
        help="Database URL (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--if-exists", choices=["replace", "append", "fail"], default="replace",
        help="Behavior if table exists (default: replace)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=10_000,
        help="Batch size for insertion (default: 10000)",
    )

    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("No database URL. Use --db-url or set DATABASE_URL env var.")
        sys.exit(1)

    if not args.source.exists():
        logger.error("Source file not found: %s", args.source)
        sys.exit(1)

    load_data(
        source=args.source,
        table=args.table,
        db_url=db_url,
        if_exists=args.if_exists,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
