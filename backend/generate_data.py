"""
Generate 250K synthetic Indian digital payment transactions into SQLite.

Schema (17 dimensions):
  transaction_id, timestamp, transaction_type, amount_inr, transaction_status,
  merchant_category, sender_bank, receiver_bank, sender_state, sender_age_group,
  receiver_age_group, device_type, network_type, fraud_flag,
  hour_of_day, day_of_week, is_weekend
"""

import random
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

NUM_ROWS = 250_000
DB_PATH = Path(__file__).parent / "insightxpert.db"

# -- Domain values --

TRANSACTION_TYPES = ["P2P", "P2M", "Bill Payment", "Recharge"]
TRANSACTION_STATUSES = ["SUCCESS", "FAILED", "PENDING"]
STATUS_WEIGHTS = [0.85, 0.10, 0.05]

MERCHANT_CATEGORIES = [
    "Food", "Grocery", "Fuel", "Entertainment", "Shopping",
    "Healthcare", "Education", "Transport", "Utilities", "Other",
]

BANKS = ["SBI", "HDFC", "ICICI", "Axis", "PNB", "Kotak", "IndusInd", "Yes Bank"]

# Weights reflect population size × digital-payment adoption (UPI penetration,
# urbanisation, smartphone density).  Large, digitally-active states get the
# highest share; small / remote UTs get a realistic but non-zero tail.
STATE_WEIGHTS = {
    # -- 28 States --
    "Maharashtra":        12.0,   # large pop + Mumbai/Pune fintech hub
    "Uttar Pradesh":      10.0,   # largest pop, moderate digital adoption
    "Karnataka":           8.0,   # Bengaluru tech hub, high UPI usage
    "Tamil Nadu":          7.0,   # Chennai + high urbanisation
    "Gujarat":             6.0,   # industrialised, high merchant payments
    "Rajasthan":           4.5,   # large pop, growing digital
    "West Bengal":         4.0,   # Kolkata metro, moderate adoption
    "Madhya Pradesh":      3.5,   # large pop, lower digital penetration
    "Andhra Pradesh":      3.5,   # Vizag/Vijayawada corridors
    "Kerala":              3.5,   # high literacy & banking penetration
    "Telangana":           5.0,   # Hyderabad tech hub, punches above pop
    "Bihar":               2.5,   # very large pop but low digital infra
    "Punjab":              2.5,   # affluent, moderate pop
    "Haryana":             2.5,   # Gurugram/NCR spillover
    "Odisha":              1.8,   # growing digital, moderate pop
    "Jharkhand":           1.5,   # industrial pockets, lower adoption
    "Chhattisgarh":        1.2,   # smaller, lower digital
    "Assam":               1.2,   # largest NE state
    "Uttarakhand":         0.9,   # small pop, moderate digital
    "Himachal Pradesh":    0.6,   # small pop, decent banking
    "Goa":                 0.5,   # tiny pop but very high per-capita digital
    "Tripura":             0.25,
    "Meghalaya":           0.20,
    "Manipur":             0.18,
    "Nagaland":            0.12,
    "Arunachal Pradesh":   0.10,
    "Mizoram":             0.10,
    "Sikkim":              0.08,
    # -- 8 Union Territories --
    "Delhi":               7.0,   # national capital, massive UPI volume
    "Chandigarh":          0.5,   # affluent UT, high per-capita digital
    "Jammu and Kashmir":   0.8,   # moderate pop
    "Puducherry":          0.25,
    "Dadra and Nagar Haveli and Daman and Diu": 0.10,
    "Andaman and Nicobar Islands":              0.05,
    "Ladakh":              0.04,
    "Lakshadweep":         0.02,
}
STATES = list(STATE_WEIGHTS.keys())
STATE_WEIGHT_VALUES = list(STATE_WEIGHTS.values())

AGE_GROUPS = ["18-25", "26-35", "36-45", "46-55", "56+"]
AGE_WEIGHTS = [0.25, 0.35, 0.20, 0.12, 0.08]

DEVICE_TYPES = ["Android", "iOS", "Web"]
DEVICE_WEIGHTS = [0.60, 0.25, 0.15]

NETWORK_TYPES = ["4G", "5G", "WiFi", "3G"]
NETWORK_WEIGHTS = [0.40, 0.25, 0.25, 0.10]

# Time range: 6 months of data
START_DATE = datetime(2024, 7, 1)
END_DATE = datetime(2024, 12, 31)
DATE_RANGE_SECONDS = int((END_DATE - START_DATE).total_seconds())


def random_timestamp() -> datetime:
    offset = random.randint(0, DATE_RANGE_SECONDS)
    return START_DATE + timedelta(seconds=offset)


def random_amount(txn_type: str) -> float:
    """Amount distribution varies by transaction type."""
    if txn_type == "P2P":
        return round(random.lognormvariate(6.5, 1.2), 2)   # median ~665
    elif txn_type == "P2M":
        return round(random.lognormvariate(5.8, 1.0), 2)   # median ~330
    elif txn_type == "Bill Payment":
        return round(random.lognormvariate(7.0, 0.8), 2)   # median ~1097
    else:  # Recharge
        return round(random.uniform(10, 2000), 2)


def generate_row() -> tuple:
    txn_id = str(uuid.uuid4())
    ts = random_timestamp()
    txn_type = random.choice(TRANSACTION_TYPES)
    amount = min(random_amount(txn_type), 500_000)  # cap at 5L
    status = random.choices(TRANSACTION_STATUSES, STATUS_WEIGHTS)[0]

    # merchant_category is NULL for P2P (no merchant)
    merchant_cat = random.choice(MERCHANT_CATEGORIES) if txn_type != "P2P" else None

    sender_bank = random.choice(BANKS)
    receiver_bank = random.choice(BANKS)
    sender_state = random.choices(STATES, STATE_WEIGHT_VALUES)[0]
    sender_age = random.choices(AGE_GROUPS, AGE_WEIGHTS)[0]

    # receiver_age_group is NULL for non-P2P
    receiver_age = random.choices(AGE_GROUPS, AGE_WEIGHTS)[0] if txn_type == "P2P" else None

    device = random.choices(DEVICE_TYPES, DEVICE_WEIGHTS)[0]
    network = random.choices(NETWORK_TYPES, NETWORK_WEIGHTS)[0]

    # fraud_flag: ~3% base rate, higher for large amounts and late-night
    fraud_prob = 0.03
    if amount > 50_000:
        fraud_prob += 0.05
    if ts.hour in (22, 23, 0, 1, 2, 3):
        fraud_prob += 0.02
    fraud_flag = 1 if random.random() < fraud_prob else 0

    hour_of_day = ts.hour
    day_of_week = ts.strftime("%A")
    is_weekend = 1 if ts.weekday() >= 5 else 0

    return (
        txn_id, ts.isoformat(), txn_type, amount, status,
        merchant_cat, sender_bank, receiver_bank, sender_state,
        sender_age, receiver_age, device, network, fraud_flag,
        hour_of_day, day_of_week, is_weekend,
    )


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("""
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
    """)

    # Create indices for common query patterns
    cur.execute("CREATE INDEX idx_txn_type ON transactions(transaction_type)")
    cur.execute("CREATE INDEX idx_status ON transactions(transaction_status)")
    cur.execute("CREATE INDEX idx_merchant ON transactions(merchant_category)")
    cur.execute("CREATE INDEX idx_sender_bank ON transactions(sender_bank)")
    cur.execute("CREATE INDEX idx_device ON transactions(device_type)")
    cur.execute("CREATE INDEX idx_fraud ON transactions(fraud_flag)")
    cur.execute("CREATE INDEX idx_hour ON transactions(hour_of_day)")
    cur.execute("CREATE INDEX idx_weekend ON transactions(is_weekend)")
    cur.execute("CREATE INDEX idx_state ON transactions(sender_state)")

    print(f"Generating {NUM_ROWS:,} transactions...")
    random.seed(42)  # reproducible

    batch_size = 10_000
    for i in range(0, NUM_ROWS, batch_size):
        rows = [generate_row() for _ in range(min(batch_size, NUM_ROWS - i))]
        cur.executemany(
            "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        print(f"  {i + len(rows):>7,} / {NUM_ROWS:,}")

    # Print summary stats
    cur.execute("SELECT COUNT(*) FROM transactions")
    total = cur.fetchone()[0]
    cur.execute("SELECT ROUND(AVG(amount_inr), 2) FROM transactions")
    avg_amt = cur.fetchone()[0]
    cur.execute("SELECT SUM(fraud_flag) FROM transactions")
    fraud_count = cur.fetchone()[0]

    print(f"\nDone! {total:,} rows in {DB_PATH}")
    print(f"  Average amount: INR {avg_amt:,.2f}")
    print(f"  Fraud-flagged:  {fraud_count:,} ({fraud_count/total*100:.1f}%)")

    conn.close()


if __name__ == "__main__":
    main()
