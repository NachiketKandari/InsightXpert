# Scope and Exclusions

**Q: What will your system deliberately not attempt to do as part of this problem?**

---

1. **Will NOT blindly execute queries without validation.** The system is designed to think before acting — it validates query intent, checks for ambiguity, and cross-checks results before presenting insights. A built-in cross-verification step ensures the system does not surface false or misleading data.

2. **Will NOT confirm or label transactions as fraudulent.** `fraud_flag` indicates flagged-for-review, not confirmed fraud. The system reports flagging patterns and rates but never declares a transaction genuinely fraudulent.

3. **Will NOT provide user-level tracking or profiling.** No `user_id` exists in the dataset, so the system cannot link transactions to individuals, build user profiles, or perform per-user risk scoring.

4. **Will NOT make causal claims.** The system surfaces correlations, trends, and patterns but will not assert that one variable causes another. All insights are framed as observed associations.

5. **Will NOT predict future trends.** Scope is limited to descriptive and diagnostic analytics over the provided dataset. No forecasting models or time-series projections.

6. **Will NOT provide real-time or streaming analytics.** The system operates on a static, pre-loaded dataset of 250K transactions — batch analysis and conversational exploration, not live ingestion.

7. **Will NOT incorporate external data sources.** All analysis is performed strictly on the supplied synthetic dataset. No census data, bank databases, or external benchmarks.
