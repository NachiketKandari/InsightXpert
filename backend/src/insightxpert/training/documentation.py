"""Business context, column descriptions, and domain rules."""

DOCUMENTATION = """
## Dataset Overview

The `transactions` table contains 250,000 Indian UPI digital payment
transactions from 2024 with 17 columns.

## Column Descriptions

| Column               | Type    | Description |
|----------------------|---------|-------------|
| transaction_id       | TEXT    | Unique identifier for each transaction (format: TXN0000000001). |
| timestamp            | TEXT    | Timestamp of the transaction (format: YYYY-MM-DD HH:MM:SS). |
| transaction_type     | TEXT    | One of: P2P, P2M, Bill Payment, Recharge. |
| merchant_category    | TEXT    | Merchant vertical.  Values: Food, Grocery, Fuel, Entertainment, Shopping, Healthcare, Education, Transport, Utilities, Other. |
| amount_inr           | REAL    | Transaction amount in Indian Rupees (range: 10 to ~42,000). |
| transaction_status   | TEXT    | One of: SUCCESS, FAILED. |
| sender_age_group     | TEXT    | Age bracket of the sender: 18-25, 26-35, 36-45, 46-55, 56+. |
| receiver_age_group   | TEXT    | Age bracket of the receiver.  Same buckets as sender_age_group. |
| sender_state         | TEXT    | Indian state of the sender.  Values: Maharashtra, Uttar Pradesh, Karnataka, Tamil Nadu, Gujarat, Rajasthan, West Bengal, Telangana, Delhi, Andhra Pradesh. |
| sender_bank          | TEXT    | Sender's bank: SBI, HDFC, ICICI, Axis, PNB, Kotak, IndusInd, Yes Bank. |
| receiver_bank        | TEXT    | Receiver's bank.  Same set of banks. |
| device_type          | TEXT    | Device used: Android, iOS, Web. |
| network_type         | TEXT    | Network at time of transaction: 4G, 5G, WiFi, 3G. |
| fraud_flag           | INTEGER | 0 = not flagged, 1 = **flagged for review** (not confirmed fraud). |
| hour_of_day          | INTEGER | Hour extracted from timestamp (0-23). |
| day_of_week          | TEXT    | Day name: Monday, Tuesday, ... Sunday. |
| is_weekend           | INTEGER | 0 = weekday, 1 = weekend (Saturday or Sunday). |

## Domain Rules & Guardrails

- **fraud_flag** means "flagged for review", **not** confirmed fraud.  Always
  use language like "flagged for review" in responses.
- **Correlation != causation.**  Surface patterns and associations but never
  assert causal relationships.
- **No user-level tracking.**  There is no `user_id` column, so repeat-behaviour
  analysis or cohort tracking is not possible.
- **Derived temporal fields** (`hour_of_day`, `day_of_week`, `is_weekend`) are
  pre-computed from `timestamp` and can be used directly.
- When sample sizes are small, flag this explicitly (e.g., "Note: based on
  320 records -- may not be representative").
- There are only 10 sender states in the dataset. Do not assume all Indian
  states/UTs are present.
- Transaction statuses are only SUCCESS or FAILED (no PENDING).
""".strip()
