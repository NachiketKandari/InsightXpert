# Question 1: Problem Understanding

**Q: In your own words, explain what this problem is asking you to build and what kind of insights a leadership-level user should be able to obtain from your system.**

---

## Answer

The challenge asks us to build a conversational AI system that bridges the gap between raw transactional data and actionable business intelligence — enabling non-technical leadership (product managers, operations heads, risk officers) to ask questions in plain English and receive accurate, well-explained insights.

Our approach is a pipeline: (1) understand the data schema, (2) interpret the user's natural language query via an LLM, (3) generate a SQL query using the schema and query as context (with RAG-based schema selection if needed), (4) execute that query against the dataset via a SQL execution tool/MCP, (5) analyze the retrieved data in the context of the original question, (6) generate insights on an interface with citations, visualizations, and recommendations where applicable. All of this wrapped in a conversational UI with context history, deep-dive options, and ambiguity detection — the system asks clarifying questions when a query is too vague rather than guessing.

The dataset spans 17 dimensions (transaction type, merchant category, geography, demographics, device/network metadata, temporal patterns, fraud indicators) across 250K synthetic Indian digital payment transactions. This means leadership-relevant insights are broad: a product leader can ask about adoption trends across age groups or device types, an operations head can investigate failure rates by bank or network type, a marketing strategist can identify high-value merchant categories by region, and a risk officer can surface fraud-flag patterns correlated with time of day, transaction size, or sender demographics — ranging from wide-scope aggregations (averages, failure rates) to narrow, multi-dimensional drill-downs filtering across multiple columns for pinpointed resolution.
