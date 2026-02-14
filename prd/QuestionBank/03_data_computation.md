# Data Computation Explanation

**Q: Choose one question from the previous response and explain how you would compute the answer using the dataset schema.**

---

**Selected Question (Risk/Operational):** Which sender banks and device types show a disproportionately high fraud-flag rate during late-night hours (22:00–04:00) on weekends, and how does this compare to their overall baseline?

**Step 1 — Filter:** Keep rows where `hour_of_day` is in {22, 23, 0, 1, 2, 3} AND `is_weekend` = 1.

**Step 2 — Group:** Group filtered data by `sender_bank` × `device_type`.

**Step 3 — Compute flag rate:** For each group, calculate fraud-flag rate = SUM(`fraud_flag`) / COUNT(*).

**Step 4 — Compute baseline:** Separately compute each bank × device combination's overall fraud-flag rate across the entire dataset (no time/weekend filter).

**Step 5 — Compare:** Divide the late-night-weekend rate by the baseline rate to get a relative risk ratio. Rank by this ratio descending to surface the most disproportionately flagged segments. A ratio > 1 indicates disproportionate flagging during late-night weekends.

## Columns Used

| Column | Role |
|---|---|
| `hour_of_day` | Filter for late-night window (22, 23, 0, 1, 2, 3) |
| `is_weekend` | Filter for weekends (1 = weekend) |
| `sender_bank` | Grouping variable (SBI, HDFC, ICICI, Axis, PNB, Kotak, IndusInd, Yes Bank) |
| `device_type` | Grouping variable (Android, iOS, Web) |
| `fraud_flag` | Aggregation target (0 = not flagged, 1 = flagged for review) |

## SQL Query

```sql
WITH late_night_weekend AS (
    SELECT
        sender_bank,
        device_type,
        COUNT(*) AS total_txns,
        SUM(fraud_flag) AS flagged_txns,
        ROUND(SUM(fraud_flag) * 1.0 / COUNT(*), 4) AS flag_rate
    FROM transactions
    WHERE hour_of_day IN (22, 23, 0, 1, 2, 3)
      AND is_weekend = 1
    GROUP BY sender_bank, device_type
),
baseline AS (
    SELECT
        sender_bank,
        device_type,
        COUNT(*) AS total_txns,
        SUM(fraud_flag) AS flagged_txns,
        ROUND(SUM(fraud_flag) * 1.0 / COUNT(*), 4) AS baseline_flag_rate
    FROM transactions
    GROUP BY sender_bank, device_type
)
SELECT
    l.sender_bank,
    l.device_type,
    l.total_txns AS late_night_wknd_txns,
    l.flagged_txns AS late_night_wknd_flagged,
    l.flag_rate AS late_night_wknd_flag_rate,
    b.total_txns AS overall_txns,
    b.baseline_flag_rate,
    ROUND(l.flag_rate / NULLIF(b.baseline_flag_rate, 0), 2) AS risk_ratio
FROM late_night_weekend l
JOIN baseline b
  ON l.sender_bank = b.sender_bank
 AND l.device_type = b.device_type
ORDER BY risk_ratio DESC;
```
