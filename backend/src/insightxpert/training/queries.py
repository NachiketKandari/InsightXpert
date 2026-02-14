"""Example question-SQL pairs for training across all 6 challenge categories."""

EXAMPLE_QUERIES: list[dict[str, str]] = [
    # -- Descriptive --
    {
        "question": "What is the average transaction amount for bill payments?",
        "sql": (
            "SELECT ROUND(AVG(amount_inr), 2) AS avg_amount "
            "FROM transactions "
            "WHERE transaction_type = 'Bill Payment';"
        ),
    },
    {
        "question": "How many transactions are in the dataset and what is the overall success rate?",
        "sql": (
            "SELECT COUNT(*) AS total_txns, "
            "ROUND(SUM(CASE WHEN transaction_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS success_rate_pct "
            "FROM transactions;"
        ),
    },
    # -- Comparative --
    {
        "question": "How do failure rates compare between Android and iOS users?",
        "sql": (
            "SELECT device_type, "
            "COUNT(*) AS total_txns, "
            "ROUND(SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS failure_rate_pct "
            "FROM transactions "
            "WHERE device_type IN ('Android', 'iOS') "
            "GROUP BY device_type;"
        ),
    },
    {
        "question": "Compare the average transaction amount across all transaction types.",
        "sql": (
            "SELECT transaction_type, "
            "ROUND(AVG(amount_inr), 2) AS avg_amount, "
            "COUNT(*) AS txn_count "
            "FROM transactions "
            "GROUP BY transaction_type "
            "ORDER BY avg_amount DESC;"
        ),
    },
    # -- Temporal --
    {
        "question": "What are the peak transaction hours for food delivery?",
        "sql": (
            "SELECT hour_of_day, COUNT(*) AS txn_count "
            "FROM transactions "
            "WHERE merchant_category = 'Food' "
            "GROUP BY hour_of_day "
            "ORDER BY txn_count DESC "
            "LIMIT 5;"
        ),
    },
    {
        "question": "How does transaction volume differ between weekdays and weekends?",
        "sql": (
            "SELECT CASE WHEN is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type, "
            "COUNT(*) AS txn_count, "
            "ROUND(AVG(amount_inr), 2) AS avg_amount "
            "FROM transactions "
            "GROUP BY is_weekend;"
        ),
    },
    # -- Segmentation --
    {
        "question": "Which age group uses P2P transfers most frequently?",
        "sql": (
            "SELECT sender_age_group, COUNT(*) AS p2p_count "
            "FROM transactions "
            "WHERE transaction_type = 'P2P' "
            "GROUP BY sender_age_group "
            "ORDER BY p2p_count DESC;"
        ),
    },
    {
        "question": "What is the transaction volume breakdown by sender state for the top 10 states?",
        "sql": (
            "SELECT sender_state, COUNT(*) AS txn_count, "
            "ROUND(SUM(amount_inr), 2) AS total_amount "
            "FROM transactions "
            "GROUP BY sender_state "
            "ORDER BY txn_count DESC "
            "LIMIT 10;"
        ),
    },
    # -- Correlation --
    {
        "question": "Is there a relationship between network type and transaction success?",
        "sql": (
            "SELECT network_type, "
            "COUNT(*) AS total_txns, "
            "ROUND(SUM(CASE WHEN transaction_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS success_rate_pct, "
            "ROUND(SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS failure_rate_pct "
            "FROM transactions "
            "GROUP BY network_type "
            "ORDER BY success_rate_pct DESC;"
        ),
    },
    {
        "question": "Do high-value transactions fail more often than low-value ones?",
        "sql": (
            "SELECT "
            "CASE WHEN amount_inr >= 10000 THEN 'High (>=10K)' "
            "     WHEN amount_inr >= 1000  THEN 'Medium (1K-10K)' "
            "     ELSE 'Low (<1K)' END AS amount_bucket, "
            "COUNT(*) AS total_txns, "
            "ROUND(SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS failure_rate_pct "
            "FROM transactions "
            "GROUP BY amount_bucket "
            "ORDER BY failure_rate_pct DESC;"
        ),
    },
    # -- Risk Analysis --
    {
        "question": "What percentage of high-value transactions are flagged for review?",
        "sql": (
            "SELECT "
            "COUNT(*) AS high_value_txns, "
            "SUM(fraud_flag) AS flagged_count, "
            "ROUND(SUM(fraud_flag) * 100.0 / COUNT(*), 2) AS flagged_pct "
            "FROM transactions "
            "WHERE amount_inr >= 10000;"
        ),
    },
    {
        "question": "Which sender banks and device types show a disproportionately high fraud-flag rate during late-night hours on weekends?",
        "sql": (
            "WITH late_night_weekend AS ( "
            "    SELECT sender_bank, device_type, "
            "        COUNT(*) AS total_txns, "
            "        SUM(fraud_flag) AS flagged_txns, "
            "        ROUND(SUM(fraud_flag) * 1.0 / COUNT(*), 4) AS flag_rate "
            "    FROM transactions "
            "    WHERE hour_of_day IN (22, 23, 0, 1, 2, 3) AND is_weekend = 1 "
            "    GROUP BY sender_bank, device_type "
            "), "
            "baseline AS ( "
            "    SELECT sender_bank, device_type, "
            "        COUNT(*) AS total_txns, "
            "        SUM(fraud_flag) AS flagged_txns, "
            "        ROUND(SUM(fraud_flag) * 1.0 / COUNT(*), 4) AS baseline_flag_rate "
            "    FROM transactions "
            "    GROUP BY sender_bank, device_type "
            ") "
            "SELECT l.sender_bank, l.device_type, "
            "    l.total_txns AS late_night_wknd_txns, "
            "    l.flag_rate  AS late_night_wknd_flag_rate, "
            "    b.baseline_flag_rate, "
            "    ROUND(l.flag_rate / NULLIF(b.baseline_flag_rate, 0), 2) AS risk_ratio "
            "FROM late_night_weekend l "
            "JOIN baseline b ON l.sender_bank = b.sender_bank AND l.device_type = b.device_type "
            "ORDER BY risk_ratio DESC;"
        ),
    },
]
