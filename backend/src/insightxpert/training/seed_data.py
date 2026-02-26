"""Column metadata for seeding the dataset_columns table.

Each entry maps directly to a DatasetColumn row. Keeping this here
(co-located with the DDL and documentation) ensures schema changes only
need to be made in one place.
"""

from __future__ import annotations

COLUMNS_META: list[dict] = [
    {
        "column_name": "transaction_id",
        "column_type": "TEXT",
        "description": "Unique identifier for each transaction (format: TXN0000000001).",
        "domain_values": None,
        "domain_rules": None,
    },
    {
        "column_name": "timestamp",
        "column_type": "TEXT",
        "description": "Timestamp of the transaction (format: YYYY-MM-DD HH:MM:SS).",
        "domain_values": None,
        "domain_rules": None,
    },
    {
        "column_name": "transaction_type",
        "column_type": "TEXT",
        "description": "Type of transaction.",
        "domain_values": '["P2P", "P2M", "Bill Payment", "Recharge"]',
        "domain_rules": None,
    },
    {
        "column_name": "merchant_category",
        "column_type": "TEXT",
        "description": "Merchant vertical.",
        "domain_values": '["Food", "Grocery", "Fuel", "Entertainment", "Shopping", "Healthcare", "Education", "Transport", "Utilities", "Other"]',
        "domain_rules": None,
    },
    {
        "column_name": "amount_inr",
        "column_type": "REAL",
        "description": "Transaction amount in Indian Rupees (range: 10 to ~42,000).",
        "domain_values": None,
        "domain_rules": None,
    },
    {
        "column_name": "transaction_status",
        "column_type": "TEXT",
        "description": "Transaction outcome.",
        "domain_values": '["SUCCESS", "FAILED"]',
        "domain_rules": None,
    },
    {
        "column_name": "sender_age_group",
        "column_type": "TEXT",
        "description": "Age bracket of the sender.",
        "domain_values": '["18-25", "26-35", "36-45", "46-55", "56+"]',
        "domain_rules": None,
    },
    {
        "column_name": "receiver_age_group",
        "column_type": "TEXT",
        "description": "Age bracket of the receiver.",
        "domain_values": '["18-25", "26-35", "36-45", "46-55", "56+"]',
        "domain_rules": None,
    },
    {
        "column_name": "sender_state",
        "column_type": "TEXT",
        "description": "Indian state of the sender.",
        "domain_values": '["Maharashtra", "Uttar Pradesh", "Karnataka", "Tamil Nadu", "Gujarat", "Rajasthan", "West Bengal", "Telangana", "Delhi", "Andhra Pradesh"]',
        "domain_rules": None,
    },
    {
        "column_name": "sender_bank",
        "column_type": "TEXT",
        "description": "Sender's bank.",
        "domain_values": '["SBI", "HDFC", "ICICI", "Axis", "PNB", "Kotak", "IndusInd", "Yes Bank"]',
        "domain_rules": None,
    },
    {
        "column_name": "receiver_bank",
        "column_type": "TEXT",
        "description": "Receiver's bank.",
        "domain_values": '["SBI", "HDFC", "ICICI", "Axis", "PNB", "Kotak", "IndusInd", "Yes Bank"]',
        "domain_rules": None,
    },
    {
        "column_name": "device_type",
        "column_type": "TEXT",
        "description": "Device used for the transaction.",
        "domain_values": '["Android", "iOS", "Web"]',
        "domain_rules": None,
    },
    {
        "column_name": "network_type",
        "column_type": "TEXT",
        "description": "Network at time of transaction.",
        "domain_values": '["4G", "5G", "WiFi", "3G"]',
        "domain_rules": None,
    },
    {
        "column_name": "fraud_flag",
        "column_type": "INTEGER",
        "description": "Fraud review flag.",
        "domain_values": None,
        "domain_rules": "0 = not flagged, 1 = flagged for review (not confirmed fraud)",
    },
    {
        "column_name": "hour_of_day",
        "column_type": "INTEGER",
        "description": "Hour extracted from timestamp (0-23).",
        "domain_values": None,
        "domain_rules": None,
    },
    {
        "column_name": "day_of_week",
        "column_type": "TEXT",
        "description": "Day name.",
        "domain_values": '["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]',
        "domain_rules": None,
    },
    {
        "column_name": "is_weekend",
        "column_type": "INTEGER",
        "description": "Weekend indicator.",
        "domain_values": None,
        "domain_rules": "0 = weekday, 1 = weekend (Saturday or Sunday)",
    },
]
