"""
Seed the Turso (libSQL) cloud database with 250K synthetic transactions.

Usage:
    # Set env vars first:
    export TURSO_DATABASE_URL=libsql://insightxpert-nachiketkandari.aws-ap-south-1.turso.io
    export TURSO_AUTH_TOKEN=<your-token>

    # Then run:
    uv run python seed_turso.py
"""

import os
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text

NUM_ROWS = 250_000

# Turso connection
TURSO_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

# SQLAlchemy URL: sqlite+libsql:// prefix + Turso host
SA_URL = f"sqlite+{TURSO_URL}?secure=true"

# -- Domain values (same as generate_data.py) --

TRANSACTION_TYPES = ["P2P", "P2M", "Bill Payment", "Recharge"]
TRANSACTION_STATUSES = ["SUCCESS", "FAILED", "PENDING"]
STATUS_WEIGHTS = [0.85, 0.10, 0.05]

MERCHANT_CATEGORIES = [
    "Food", "Grocery", "Fuel", "Entertainment", "Shopping",
    "Healthcare", "Education", "Transport", "Utilities", "Other",
]

BANKS = ["SBI", "HDFC", "ICICI", "Axis", "PNB", "Kotak", "IndusInd", "Yes Bank"]

STATES = [
    "Maharashtra", "Karnataka", "Tamil Nadu", "Delhi", "Uttar Pradesh",
    "Gujarat", "Rajasthan", "West Bengal", "Telangana", "Kerala",
    "Madhya Pradesh", "Bihar", "Andhra Pradesh", "Punjab", "Haryana",
]

AGE_GROUPS = ["18-25", "26-35", "36-45", "46-55", "56+"]
AGE_WEIGHTS = [0.25, 0.35, 0.20, 0.12, 0.08]

DEVICE_TYPES = ["Android", "iOS", "Web"]
DEVICE_WEIGHTS = [0.60, 0.25, 0.15]

NETWORK_TYPES = ["4G", "5G", "WiFi", "3G"]
NETWORK_WEIGHTS = [0.40, 0.25, 0.25, 0.10]

START_DATE = datetime(2024, 7, 1)
END_DATE = datetime(2024, 12, 31)
DATE_RANGE_SECONDS = int((END_DATE - START_DATE).total_seconds())


def random_timestamp() -> datetime:
    offset = random.randint(0, DATE_RANGE_SECONDS)
    return START_DATE + timedelta(seconds=offset)


def random_amount(txn_type: str) -> float:
    if txn_type == "P2P":
        return round(random.lognormvariate(6.5, 1.2), 2)
    elif txn_type == "P2M":
        return round(random.lognormvariate(5.8, 1.0), 2)
    elif txn_type == "Bill Payment":
        return round(random.lognormvariate(7.0, 0.8), 2)
    else:
        return round(random.uniform(10, 2000), 2)


def generate_row() -> dict:
    txn_type = random.choice(TRANSACTION_TYPES)
    ts = random_timestamp()
    amount = min(random_amount(txn_type), 500_000)

    fraud_prob = 0.03
    if amount > 50_000:
        fraud_prob += 0.05
    if ts.hour in (22, 23, 0, 1, 2, 3):
        fraud_prob += 0.02

    return {
        "transaction_id": str(uuid.uuid4()),
        "timestamp": ts.isoformat(),
        "transaction_type": txn_type,
        "amount_inr": amount,
        "transaction_status": random.choices(TRANSACTION_STATUSES, STATUS_WEIGHTS)[0],
        "merchant_category": random.choice(MERCHANT_CATEGORIES) if txn_type != "P2P" else None,
        "sender_bank": random.choice(BANKS),
        "receiver_bank": random.choice(BANKS),
        "sender_state": random.choice(STATES),
        "sender_age_group": random.choices(AGE_GROUPS, AGE_WEIGHTS)[0],
        "receiver_age_group": random.choices(AGE_GROUPS, AGE_WEIGHTS)[0] if txn_type == "P2P" else None,
        "device_type": random.choices(DEVICE_TYPES, DEVICE_WEIGHTS)[0],
        "network_type": random.choices(NETWORK_TYPES, NETWORK_WEIGHTS)[0],
        "fraud_flag": 1 if random.random() < fraud_prob else 0,
        "hour_of_day": ts.hour,
        "day_of_week": ts.strftime("%A"),
        "is_weekend": 1 if ts.weekday() >= 5 else 0,
    }


INSERT_SQL = text("""
    INSERT INTO transactions (
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


def main() -> None:
    print(f"Connecting to Turso: {TURSO_URL}")
    engine = create_engine(SA_URL, connect_args={"auth_token": TURSO_TOKEN})

    with engine.connect() as conn:
        # Drop existing table if any
        conn.execute(text("DROP TABLE IF EXISTS transactions"))
        conn.commit()

        # Create table
        conn.execute(text("""
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
        """))
        conn.commit()
        print("Table created.")

        # Create indices
        for idx_sql in [
            "CREATE INDEX idx_txn_type ON transactions(transaction_type)",
            "CREATE INDEX idx_status ON transactions(transaction_status)",
            "CREATE INDEX idx_merchant ON transactions(merchant_category)",
            "CREATE INDEX idx_sender_bank ON transactions(sender_bank)",
            "CREATE INDEX idx_device ON transactions(device_type)",
            "CREATE INDEX idx_fraud ON transactions(fraud_flag)",
            "CREATE INDEX idx_hour ON transactions(hour_of_day)",
            "CREATE INDEX idx_weekend ON transactions(is_weekend)",
            "CREATE INDEX idx_state ON transactions(sender_state)",
        ]:
            conn.execute(text(idx_sql))
        conn.commit()
        print("Indices created.")

        # Seed data in batches
        print(f"Generating {NUM_ROWS:,} transactions...")
        random.seed(42)

        batch_size = 1_000  # smaller batches for network writes
        for i in range(0, NUM_ROWS, batch_size):
            count = min(batch_size, NUM_ROWS - i)
            rows = [generate_row() for _ in range(count)]
            conn.execute(INSERT_SQL, rows)
            conn.commit()
            done = i + count
            if done % 10_000 == 0 or done == NUM_ROWS:
                print(f"  {done:>7,} / {NUM_ROWS:,}")

        # Verify
        total = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
        avg_amt = conn.execute(text("SELECT ROUND(AVG(amount_inr), 2) FROM transactions")).scalar()
        fraud_count = conn.execute(text("SELECT SUM(fraud_flag) FROM transactions")).scalar()

    print(f"\nDone! {total:,} rows in Turso")
    print(f"  Average amount: INR {avg_amt:,.2f}")
    print(f"  Fraud-flagged:  {fraud_count:,} ({fraud_count/total*100:.1f}%)")

    engine.dispose()


if __name__ == "__main__":
    main()
