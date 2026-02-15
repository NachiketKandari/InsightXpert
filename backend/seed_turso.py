"""
Seed the Turso (libSQL) cloud database with data from upi_transactions_2024.csv.

Supports resuming — skips rows already in Turso and inserts only missing ones.
Reconnects between batches to avoid connection timeouts.

Usage:
    # Set env vars first:
    export TURSO_DATABASE_URL=libsql://insightxpert-nachiketkandari.aws-ap-south-1.turso.io
    export TURSO_AUTH_TOKEN=<your-token>

    # Fresh load (drops and recreates table):
    uv run python seed_turso.py --fresh

    # Resume (default — skips existing rows):
    uv run python seed_turso.py
"""

import csv
import os
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

CSV_PATH = Path(__file__).parent / "upi_transactions_2024.csv"

# Turso connection
TURSO_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_TOKEN = os.environ["TURSO_AUTH_TOKEN"]
SA_URL = f"sqlite+{TURSO_URL}?secure=true"

# Map CSV column names → DB column names
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

INSERT_SQL = text("""
    INSERT OR IGNORE INTO transactions (
        transaction_id, timestamp, transaction_type, amount_inr, transaction_status,
        merchant_category, sender_bank, receiver_bank, sender_state, sender_age_group,
        receiver_age_group, device_type, network_type, fraud_flag,
        hour_of_day, day_of_week, is_weekend
    ) VALUES (
        :transaction_id, :timestamp, :transaction_type, :amount_inr, :transaction_status,
        :merchant_category, :sender_bank, :receiver_bank, :sender_state, :sender_age_group,
        :receiver_age_group, :device_type, :network_type, :fraud_flag,
        :hour_of_day, :day_of_week, :is_weekend
    )
""")

CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id    TEXT PRIMARY KEY,
        timestamp         TEXT NOT NULL,
        transaction_type  TEXT NOT NULL,
        amount_inr        REAL NOT NULL,
        transaction_status TEXT NOT NULL,
        merchant_category TEXT,
        sender_bank       TEXT NOT NULL,
        receiver_bank     TEXT NOT NULL,
        sender_state      TEXT NOT NULL,
        sender_age_group  TEXT NOT NULL,
        receiver_age_group TEXT,
        device_type       TEXT NOT NULL,
        network_type      TEXT NOT NULL,
        fraud_flag        INTEGER NOT NULL DEFAULT 0,
        hour_of_day       INTEGER NOT NULL,
        day_of_week       TEXT NOT NULL,
        is_weekend        INTEGER NOT NULL DEFAULT 0
    )
"""

INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS idx_txn_type ON transactions(transaction_type)",
    "CREATE INDEX IF NOT EXISTS idx_status ON transactions(transaction_status)",
    "CREATE INDEX IF NOT EXISTS idx_merchant ON transactions(merchant_category)",
    "CREATE INDEX IF NOT EXISTS idx_sender_bank ON transactions(sender_bank)",
    "CREATE INDEX IF NOT EXISTS idx_device ON transactions(device_type)",
    "CREATE INDEX IF NOT EXISTS idx_fraud ON transactions(fraud_flag)",
    "CREATE INDEX IF NOT EXISTS idx_hour ON transactions(hour_of_day)",
    "CREATE INDEX IF NOT EXISTS idx_weekend ON transactions(is_weekend)",
    "CREATE INDEX IF NOT EXISTS idx_state ON transactions(sender_state)",
]


def make_engine():
    return create_engine(SA_URL, connect_args={"auth_token": TURSO_TOKEN})


def csv_row_to_dict(row: dict) -> dict:
    mapped = {}
    for csv_col, db_col in COLUMN_MAP.items():
        val = row[csv_col].strip()
        if db_col == "amount_inr":
            val = float(val)
        elif db_col in ("fraud_flag", "hour_of_day", "is_weekend"):
            val = int(val)
        elif val == "":
            val = None
        mapped[db_col] = val
    return mapped


def execute_with_retry(fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(wait)
            else:
                raise


def main() -> None:
    fresh = "--fresh" in sys.argv

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    print(f"Connecting to Turso: {TURSO_URL}", flush=True)

    if fresh:
        engine = make_engine()
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS transactions"))
            conn.commit()
            print("Dropped existing table.", flush=True)
        engine.dispose()

    # Ensure table and indices exist
    engine = make_engine()
    with engine.connect() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        conn.commit()
        for idx_sql in INDEX_SQLS:
            conn.execute(text(idx_sql))
        conn.commit()
        existing = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
    engine.dispose()
    print(f"Table ready. Existing rows: {existing:,}", flush=True)

    # Load CSV in batches, reconnecting each batch
    print(f"Loading data from {CSV_PATH}...", flush=True)
    batch_size = 500
    batch: list[dict] = []
    total_read = 0
    total_inserted = 0

    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_read += 1
            batch.append(csv_row_to_dict(row))

            if len(batch) >= batch_size:
                def insert_batch(b=batch[:]):
                    eng = make_engine()
                    with eng.connect() as c:
                        c.execute(INSERT_SQL, b)
                        c.commit()
                    eng.dispose()

                execute_with_retry(insert_batch)
                total_inserted += len(batch)
                if total_inserted % 5_000 == 0:
                    print(f"  {total_inserted:>7,} / 250,000 rows processed", flush=True)
                batch.clear()

        if batch:
            def insert_batch(b=batch[:]):
                eng = make_engine()
                with eng.connect() as c:
                    c.execute(INSERT_SQL, b)
                    c.commit()
                eng.dispose()

            execute_with_retry(insert_batch)
            total_inserted += len(batch)

    # Verify
    engine = make_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
        avg_amt = conn.execute(text("SELECT ROUND(AVG(amount_inr), 2) FROM transactions")).scalar()
        fraud_count = conn.execute(text("SELECT SUM(fraud_flag) FROM transactions")).scalar()
    engine.dispose()

    print(f"\nDone! {count:,} rows in Turso", flush=True)
    print(f"  Average amount: INR {avg_amt:,.2f}", flush=True)
    print(f"  Fraud-flagged:  {fraud_count:,} ({fraud_count/count*100:.1f}%)", flush=True)


if __name__ == "__main__":
    main()
