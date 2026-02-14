"""Business context, column descriptions, and domain rules."""

DOCUMENTATION = """
## Dataset Overview

The `transactions` table contains 250,000 synthetic Indian digital payment
transactions with 17 columns.  All insights derived from this data are
**directional** (synthetic data) and should not be treated as absolute.

## Column Descriptions

| Column               | Type    | Description |
|----------------------|---------|-------------|
| transaction_id       | TEXT    | Unique identifier for each transaction. |
| timestamp            | TEXT    | ISO-8601 timestamp of the transaction. |
| transaction_type     | TEXT    | One of: P2P, P2M, Bill Payment, Recharge. |
| merchant_category    | TEXT    | Merchant vertical.  Values: Food, Grocery, Fuel, Entertainment, Shopping, Healthcare, Education, Transport, Utilities, Other.  **NULL for P2P transactions** (no merchant involved). |
| amount_inr           | REAL    | Transaction amount in Indian Rupees. |
| transaction_status   | TEXT    | One of: SUCCESS, FAILED, PENDING. |
| sender_age_group     | TEXT    | Age bracket of the sender: 18-25, 26-35, 36-45, 46-60, 60+. |
| receiver_age_group   | TEXT    | Age bracket of the receiver.  Same buckets as sender_age_group.  **NULL for non-P2P transactions** (receiver is a merchant or biller). |
| sender_state         | TEXT    | Indian state of the sender. |
| sender_bank          | TEXT    | Sender's bank: SBI, HDFC, ICICI, Axis, PNB, Kotak, IndusInd, Yes Bank. |
| receiver_bank        | TEXT    | Receiver's bank.  Same set of banks. |
| device_type          | TEXT    | Device used: Android, iOS, Web. |
| network_type         | TEXT    | Network at time of transaction: 4G, 5G, WiFi, 3G. |
| fraud_flag           | INTEGER | 0 = not flagged, 1 = **flagged for review** (not confirmed fraud). |
| hour_of_day          | INTEGER | Hour extracted from timestamp (0-23). |
| day_of_week          | TEXT    | Day name: Monday, Tuesday, ... Sunday. |
| is_weekend           | INTEGER | 0 = weekday, 1 = weekend (Saturday or Sunday). |

## NULL Semantics

- `merchant_category` is NULL when `transaction_type` = 'P2P' because there is
  no merchant in a peer-to-peer transfer.  Exclude NULLs from merchant-level
  aggregations; do not impute.
- `receiver_age_group` is NULL when `transaction_type` != 'P2P' because the
  receiver is a merchant or biller, not an individual.

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
""".strip()
