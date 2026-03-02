# Dataset Documentation

## Overview

250,000 synthetic Indian digital payment transactions. The dataset models UPI-era payment patterns across multiple transaction types, banks, states, age groups, devices, and network types. It spans the full calendar year 2023 (2023-01-01 to 2023-12-31).

The CSV file is `backend/upi_transactions_2024.csv`. It is loaded into the local SQLite database via `backend/generate_data.py`, which normalises CSV column names to snake_case and creates all indices.

---

## Table Schema

```sql
CREATE TABLE transactions (
    transaction_id     TEXT PRIMARY KEY,
    timestamp          TEXT NOT NULL,
    transaction_type   TEXT NOT NULL,
    amount_inr         REAL NOT NULL,
    transaction_status TEXT NOT NULL,
    merchant_category  TEXT,
    sender_bank        TEXT NOT NULL,
    receiver_bank      TEXT NOT NULL,
    sender_state       TEXT NOT NULL,
    sender_age_group   TEXT NOT NULL,
    receiver_age_group TEXT,
    device_type        TEXT NOT NULL,
    network_type       TEXT NOT NULL,
    fraud_flag         INTEGER NOT NULL DEFAULT 0,
    hour_of_day        INTEGER NOT NULL,
    day_of_week        TEXT NOT NULL,
    is_weekend         INTEGER NOT NULL DEFAULT 0
);
```

### Column Descriptions

| Column | Type | Description |
|---|---|---|
| `transaction_id` | TEXT | Unique UUID per transaction. Primary key. |
| `timestamp` | TEXT | ISO 8601 datetime string. Covers 2023-01-01 to 2023-12-31. |
| `transaction_type` | TEXT | `P2P`, `P2M`, `Bill Payment`, or `Recharge` |
| `amount_inr` | REAL | Transaction amount in Indian Rupees (INR). |
| `transaction_status` | TEXT | `SUCCESS`, `FAILED`, or `PENDING` |
| `merchant_category` | TEXT | Category of the merchant. NULL for P2P transactions. Values: `Food`, `Grocery`, `Fuel`, `Entertainment`, `Shopping`, `Healthcare`, `Education`, `Transport`, `Utilities`, `Other` |
| `sender_bank` | TEXT | Sending bank. Values: HDFC, SBI, ICICI, Axis, Kotak, Yes, PNB, BOB, Union, Canara |
| `receiver_bank` | TEXT | Receiving bank. Same set of values as `sender_bank`. |
| `sender_state` | TEXT | Indian state of the sender. All 28 states and 8 union territories are represented. |
| `sender_age_group` | TEXT | Age bracket of the sender: `18-25`, `26-35`, `36-45`, `46-55`, `55+` |
| `receiver_age_group` | TEXT | Age bracket of the receiver. Same categories. May be NULL for merchant-side receivers. |
| `device_type` | TEXT | Device used to initiate the transaction: `Android`, `iOS`, `Web` |
| `network_type` | TEXT | Network at time of transaction: `4G`, `5G`, `WiFi`, `3G` |
| `fraud_flag` | INTEGER | `0` = not flagged. `1` = flagged for review. This is **not confirmed fraud** — it is a risk signal. |
| `hour_of_day` | INTEGER | Hour extracted from `timestamp`. Range 0–23. |
| `day_of_week` | TEXT | Day name extracted from `timestamp` (e.g. `Monday`, `Tuesday`, …). |
| `is_weekend` | INTEGER | `1` if Saturday or Sunday, `0` otherwise. |

---

## Indices

Nine indices are created by `generate_data.py` after loading:

| Index name | Column(s) |
|---|---|
| `idx_txn_type` | `transaction_type` |
| `idx_status` | `transaction_status` |
| `idx_merchant` | `merchant_category` |
| `idx_sender_bank` | `sender_bank` |
| `idx_device` | `device_type` |
| `idx_fraud` | `fraud_flag` |
| `idx_hour` | `hour_of_day` |
| `idx_weekend` | `is_weekend` |
| `idx_state` | `sender_state` |

---

## Pre-Computed Statistics

On first startup, `db/stats_computer.py` computes summary statistics from the transactions table and stores them in the `dataset_stats` table in the auth database. This computation is idempotent — if `dataset_stats` already has rows, it exits immediately.

These stats are injected into the LLM context as a `stats_context` chunk when `stats_context_injection` is enabled (admin feature toggle).

Statistics groups and metrics computed:

| Group | Dimension | Metrics |
|---|---|---|
| `overall` | — | `txn_count`, `date_min`, `date_max`, `avg_amount`, `failure_rate_pct`, `fraud_rate_pct`, `failure_count`, `fraud_count` |
| `transaction_type` | per `transaction_type` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `merchant_category` | per `merchant_category` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `bank` | per `sender_bank` | `txn_count`, `avg_amount_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `state` | per `sender_state` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `age_group` | per `sender_age_group` | `txn_count`, `avg_amount_inr`, `failure_count`, `failure_rate_pct` |
| `device_type` | per `device_type` | `txn_count`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `network_type` | per `network_type` | `txn_count`, `failure_count`, `failure_rate_pct` |
| `monthly` | per `YYYY-MM` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `fraud_count` |
| `hourly` | per `hour_of_day` | `txn_count`, `failure_count`, `fraud_count` |

---

## Loading Data

```bash
cd backend
python generate_data.py
```

This script:

1. Drops and recreates the `transactions` table (other tables such as `users`, `conversations`, `dataset_stats` are preserved).
2. Reads `upi_transactions_2024.csv` in 10,000-row batches and inserts via `executemany`.
3. Creates all 9 indices.

The script prints row count progress and a final total.

---

## Example Queries

These are the question→SQL pairs used as RAG training examples in `training/queries.py`. They cover all six challenge categories.

### Descriptive

**Average transaction amount for bill payments**
```sql
SELECT AVG(amount_inr) AS avg_amount
FROM transactions
WHERE transaction_type = 'Bill Payment';
```

**Overall transaction count and success rate**
```sql
SELECT
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS success_rate_pct
FROM transactions;
```

### Comparative

**Failure rate comparison: Android vs iOS**
```sql
SELECT
    device_type,
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM transactions
WHERE device_type IN ('Android', 'iOS')
GROUP BY device_type;
```

**Average transaction amount by type**
```sql
SELECT
    transaction_type,
    AVG(amount_inr) AS avg_amount,
    COUNT(*) AS txn_count
FROM transactions
GROUP BY transaction_type
ORDER BY avg_amount DESC;
```

### Temporal

**Peak transaction hours for food delivery**
```sql
SELECT hour_of_day, COUNT(*) AS txn_count
FROM transactions
WHERE merchant_category = 'Food'
GROUP BY hour_of_day
ORDER BY txn_count DESC
LIMIT 5;
```

**Weekend vs weekday transaction volume and amounts**
```sql
SELECT
    CASE WHEN is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    COUNT(*) AS txn_count,
    AVG(amount_inr) AS avg_amount
FROM transactions
GROUP BY is_weekend;
```

### Segmentation

**Age groups most active in P2P transfers**
```sql
SELECT sender_age_group, COUNT(*) AS p2p_count
FROM transactions
WHERE transaction_type = 'P2P'
GROUP BY sender_age_group
ORDER BY p2p_count DESC;
```

**State-wise transaction volume (top 10)**
```sql
SELECT
    sender_state,
    COUNT(*) AS txn_count,
    SUM(amount_inr) AS total_amount
FROM transactions
GROUP BY sender_state
ORDER BY txn_count DESC
LIMIT 10;
```

### Correlation

**Network type vs transaction success rate**
```sql
SELECT
    network_type,
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS success_rate_pct,
    SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM transactions
GROUP BY network_type
ORDER BY success_rate_pct DESC;
```

**High-value vs low-value transaction failure rates**
```sql
SELECT
    CASE
        WHEN amount_inr >= 10000 THEN 'High (>=10K)'
        WHEN amount_inr >= 1000  THEN 'Medium (1K-10K)'
        ELSE 'Low (<1K)'
    END AS amount_bucket,
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM transactions
GROUP BY amount_bucket
ORDER BY failure_rate_pct DESC;
```

### Risk Analysis

**Fraud flag rate for high-value transactions**
```sql
SELECT
    COUNT(*) AS high_value_txns,
    SUM(fraud_flag) AS flagged_count,
    SUM(fraud_flag) * 100.0 / COUNT(*) AS flagged_pct
FROM transactions
WHERE amount_inr >= 10000;
```

**Bank × device fraud-flag concentration during late-night weekends**
```sql
WITH late_night_weekend AS (
    SELECT
        sender_bank,
        device_type,
        COUNT(*) AS total_txns,
        SUM(fraud_flag) AS flagged_txns,
        SUM(fraud_flag) * 1.0 / COUNT(*) AS flag_rate
    FROM transactions
    WHERE hour_of_day IN (22, 23, 0, 1, 2, 3) AND is_weekend = 1
    GROUP BY sender_bank, device_type
),
baseline AS (
    SELECT
        sender_bank,
        device_type,
        COUNT(*) AS total_txns,
        SUM(fraud_flag) AS flagged_txns,
        SUM(fraud_flag) * 1.0 / COUNT(*) AS baseline_flag_rate
    FROM transactions
    GROUP BY sender_bank, device_type
)
SELECT
    l.sender_bank,
    l.device_type,
    l.total_txns AS late_night_wknd_txns,
    l.flag_rate AS late_night_wknd_flag_rate,
    b.baseline_flag_rate,
    l.flag_rate / NULLIF(b.baseline_flag_rate, 0) AS risk_ratio
FROM late_night_weekend l
JOIN baseline b ON l.sender_bank = b.sender_bank AND l.device_type = b.device_type
ORDER BY risk_ratio DESC;
```

---

## Important Caveats

- **Synthetic data.** All 250,000 rows were generated programmatically. Patterns are statistically plausible for Indian UPI payments but are not derived from real transactions. Insights are directional, not predictive.

- **`fraud_flag = 1` does not mean confirmed fraud.** It means the transaction was flagged for review based on risk heuristics in the data generator. Treat it as a risk signal, not a label.

- **Correlation only.** No causal relationships are present. Associations between columns (e.g. 5G and higher success rates) reflect the generation model, not real-world causality.

- **No individual user IDs.** The dataset contains no unique sender/receiver identifiers beyond `sender_bank`, `sender_state`, and `sender_age_group`. There is no way to track individual user behaviour across transactions.

- **Static dataset.** The transactions table never changes at runtime. All aggregate statistics are pre-computed once on startup and reused. The `generate_data.py` loader is the only mechanism to update the data.
