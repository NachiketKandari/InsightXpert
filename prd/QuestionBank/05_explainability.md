# Explainability Strategy

**Q: How will your system explain insights and answers to a non-technical, leadership-level user?**

---

**1. Plain-language summaries.** All internal data concepts are translated to business language. Never "COUNT where transaction_status = 'FAILED'" — always "failure rate." A terminology mapping layer ensures responses match the vocabulary leadership already uses.

**2. Layered responses.** First line: the direct answer ("Bill payment failure rates spiked to 12.3% last Thursday."). Next block: supporting evidence (breakdown by hour, banks affected, merchant categories). Follow-ups unlock deeper context (trends, cohort comparisons, contributing factors). A VP gets what they need in five seconds; a Head of Risk can drill down without switching tools.

**3. Contextual comparisons.** Numbers are never presented in isolation — every metric is anchored to a benchmark. "The 8.2% failure rate for bill payments is nearly double the platform-wide average of 4.5%." This gives immediate severity context.

**4. Data provenance.** Each response notes scope: "Based on 12,400 bill payment transactions from weekdays in Q4." Leadership can judge relevance without inspecting queries.

**5. Explain-by-example.** Where helpful, the system generates concrete examples grounded in the actual data — e.g., projecting a trend line and charting it to show *why* a pattern matters, not just *that* it exists.

**6. Visual aids.** Bar charts for comparisons, sparklines for trends, tables for ranked breakdowns. Key figures are highlighted so the most important number stands out at a glance.

**7. Confidence caveats.** Small samples are flagged explicitly ("Note: based on 320 records — may not be representative"). Correlation vs causation is always distinguished so leadership decisions are grounded in honest, qualified analysis.
