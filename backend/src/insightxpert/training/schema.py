"""DDL definitions for the transactions table."""

DDL = """
CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    timestamp TEXT,
    transaction_type TEXT,
    merchant_category TEXT,
    amount_inr DOUBLE PRECISION,
    transaction_status TEXT,
    sender_age_group TEXT,
    receiver_age_group TEXT,
    sender_state TEXT,
    sender_bank TEXT,
    receiver_bank TEXT,
    device_type TEXT,
    network_type TEXT,
    fraud_flag INTEGER,
    hour_of_day INTEGER,
    day_of_week TEXT,
    is_weekend INTEGER
);
""".strip()
