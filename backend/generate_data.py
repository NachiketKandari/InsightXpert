"""
Load UPI transaction data from CSV into local SQLite.

Reads upi_transactions_2024.csv (250K rows) and inserts into insightxpert.db.
Column mapping: CSV headers with spaces/parens are normalized to snake_case.
"""

import csv
import sqlite3
from pathlib import Path

CSV_PATH = Path(__file__).parent / "upi_transactions_2024.csv"
DB_PATH = Path(__file__).parent / "insightxpert.db"

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

DB_COLUMNS = list(COLUMN_MAP.values())

CREATE_TABLE = """
    CREATE TABLE transactions (
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

INDICES = [
    "CREATE INDEX idx_txn_type ON transactions(transaction_type)",
    "CREATE INDEX idx_status ON transactions(transaction_status)",
    "CREATE INDEX idx_merchant ON transactions(merchant_category)",
    "CREATE INDEX idx_sender_bank ON transactions(sender_bank)",
    "CREATE INDEX idx_device ON transactions(device_type)",
    "CREATE INDEX idx_fraud ON transactions(fraud_flag)",
    "CREATE INDEX idx_hour ON transactions(hour_of_day)",
    "CREATE INDEX idx_weekend ON transactions(is_weekend)",
    "CREATE INDEX idx_state ON transactions(sender_state)",
]


def csv_row_to_tuple(row: dict) -> tuple:
    """Convert a CSV row dict to a tuple in DB column order."""
    mapped = {}
    for csv_col, db_col in COLUMN_MAP.items():
        val = row[csv_col].strip()
        if db_col in ("amount_inr",):
            val = float(val)
        elif db_col in ("fraud_flag", "hour_of_day", "is_weekend"):
            val = int(val)
        elif val == "":
            val = None
        mapped[db_col] = val
    # Return in the DB column order used by CREATE TABLE
    return (
        mapped["transaction_id"],
        mapped["timestamp"],
        mapped["transaction_type"],
        mapped["amount_inr"],
        mapped["transaction_status"],
        mapped["merchant_category"],
        mapped["sender_bank"],
        mapped["receiver_bank"],
        mapped["sender_state"],
        mapped["sender_age_group"],
        mapped["receiver_age_group"],
        mapped["device_type"],
        mapped["network_type"],
        mapped["fraud_flag"],
        mapped["hour_of_day"],
        mapped["day_of_week"],
        mapped["is_weekend"],
    )


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Drop only the transactions table (preserve other tables like users, conversations)
    cur.execute("DROP TABLE IF EXISTS transactions")
    cur.execute(CREATE_TABLE)
    for idx_sql in INDICES:
        cur.execute(idx_sql)
    conn.commit()
    print("Transactions table recreated (other tables preserved).")

    print(f"Loading data from {CSV_PATH}...")
    batch_size = 10_000
    batch: list[tuple] = []
    total = 0

    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            batch.append(csv_row_to_tuple(row))
            if len(batch) >= batch_size:
                cur.executemany(
                    "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                conn.commit()
                total += len(batch)
                print(f"  {total:>7,} rows loaded")
                batch.clear()

        if batch:
            cur.executemany(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            total += len(batch)
            print(f"  {total:>7,} rows loaded")

    # Summary
    cur.execute("SELECT COUNT(*) FROM transactions")
    count = cur.fetchone()[0]
    cur.execute("SELECT ROUND(AVG(amount_inr), 2) FROM transactions")
    avg_amt = cur.fetchone()[0]
    cur.execute("SELECT SUM(fraud_flag) FROM transactions")
    fraud_count = cur.fetchone()[0]

    print(f"\nDone! {count:,} rows in {DB_PATH}")
    print(f"  Average amount: INR {avg_amt:,.2f}")
    print(f"  Fraud-flagged:  {fraud_count:,} ({fraud_count/count*100:.1f}%)")

    conn.close()


if __name__ == "__main__":
    main()
