# Assumptions and Limitations

**Q: What assumptions or limitations will your system explicitly consider while answering questions from leadership?**

---

**Data-Level:**

1. **Synthetic data = directional insights.** The 250K transactions mirror realistic patterns but may miss edge cases or seasonal anomalies present in production data. All insights are treated as directional, not absolute.

2. **Fraud flag ≠ confirmed fraud.** `fraud_flag` = 1 means flagged for review, not confirmed fraudulent. The system will use language like "flagged for review" to avoid overstating conclusions.

3. **NULLs are structural, not missing.** `merchant_category` is NULL for P2P (no merchant involved); `receiver_age_group` is NULL for non-P2P. These are excluded from irrelevant aggregations, not imputed.

4. **Derived temporal fields taken as given.** `hour_of_day`, `day_of_week`, `is_weekend` are pre-computed from timestamp and used directly.

**Analytical:**

5. **Correlation ≠ causation.** The system surfaces patterns and associations but will not assert causal relationships. Leadership is informed when findings are correlational.

6. **No user-level tracking.** No `user_id` exists, so the system cannot track repeat behavior, build user profiles, or perform cohort analysis. All insights are transaction-level.

7. **Leadership must engage in clarification.** We assume leadership is willing to participate in 2–3 turn conversations when their query exceeds our ambiguity threshold. The system will ask clarifying questions rather than guess intent.

8. **No global/industry context.** The system analyzes only the provided dataset. It cannot benchmark against industry-wide trends — e.g., a low transaction count might reflect company performance or a sector-wide downturn, and we cannot distinguish between the two. (A grounding-with-search option is a possible late-stage enhancement but not a core assumption.)
