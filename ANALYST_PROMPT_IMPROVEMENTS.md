# Analyst Prompt: Observed Gaps & Proposed Changes

Based on testing 4 complex analytical questions against the analyst in `analyst` mode.

---

## Test Results Summary

| # | Question | SQL Queries Run | Key Gap |
|---|----------|-----------------|---------|
| Q1 | Fraud flag timing x type x network | 1 | No baseline comparison, no weekend/late-night isolation |
| Q2 | Network x device x transaction type failure rates | 1 | No overall baseline rate, but otherwise solid |
| Q3 | Bank-to-bank routing friction during peak hours | 1 | Didn't filter for P2P (only type with meaningful sender->receiver routing) |
| Q4 | Generational spending x merchant categories | 1 | Didn't filter for P2M, no frequency vs. ticket-size contrast |

---

## Root Causes

### 1. Single-query habit -- no multi-step analysis

**Observation:** The analyst always writes one comprehensive SQL and synthesizes from that single result set. It never chains 2-4 queries to build layered analysis (e.g., "first get the baseline, then get the segment, then compare").

**Why it happens:**
- The agentic loop supports up to 10 iterations (`max_agent_iterations=10`), so multi-query is technically possible -- the LLM just never chooses to.
- All 12 training examples in `training/queries.py` are single SQL queries. Even the most complex one (Risk Analysis #2 -- late-night weekend fraud flags with CTE + baseline) is a single query.
- The system prompt says "Always execute the SQL with run_sql before answering" (singular) -- this subtly implies one query is sufficient.

**Impact:** Complex questions that require cross-referencing (e.g., "segment rate vs. baseline rate") get answered with a single GROUP BY that shows raw numbers but lacks the comparative context that makes insights actionable.

### 2. No "baseline-first" analysis pattern

**Observation:** None of the 4 responses computed a baseline/overall rate and compared segments against it. The expected insights all follow a pattern like "segment X is 4.5% vs baseline 0.8%" -- the analyst never produces this contrast.

**Why it happens:**
- The system prompt's Response Structure says "Supporting Evidence (key numbers, comparisons, rankings)" but doesn't specify *what* to compare against.
- No explicit instruction to compute overall/baseline metrics before drilling into segments.

**Impact:** Answers say "the highest flag rate is 3.64%" -- but 3.64% of what? Is that high or low? Without a baseline, the audience can't judge significance.

### 3. Missing domain-aware filtering rules

**Observation:**
- Q3 asks about "bank-to-bank routes" but the analyst queried ALL transaction types. Only P2P transactions have meaningful sender->receiver bank routing. P2M transactions go to merchants, not receiving banks.
- Q4 asks about "spending behavior at merchant categories" but the analyst included all transaction types. Only P2M (person-to-merchant) transactions have merchant categories; P2P, Bill Payment, and Recharge have `merchant_category = NULL` or irrelevant values.

**Why it happens:**
- The Business Context in `training/documentation.py` describes the columns and their values but doesn't encode domain rules like "bank-to-bank analysis should be scoped to P2P" or "merchant category analysis should be scoped to P2M."
- The analyst treats every column as equally applicable to every query.

**Impact:** Results include irrelevant data that dilutes the analysis. A bank-to-bank failure rate computed across P2M + Recharge + Bill Payment is misleading because those transaction types don't represent true inter-bank routing.

### 4. Response tone is correct but depth is shallow

**Observation:** The analyst follows the prescribed response structure (Direct Answer -> Evidence -> Provenance -> Caveats -> Follow-ups) but the content within each section is thin. Compare:

**What we got (Q1):**
> "The highest flag rate observed is 3.64% for Recharge transactions on Tuesday at 3 PM via 4G network."

**What we wanted:**
> "Transactions are most frequently flagged for review on weekends between 11 PM and 3 AM. During this window, P2P transfers over WiFi networks are flagged at a rate of 4.5%, compared to the baseline 0.8%. These flagged nighttime P2P transfers also have an average transaction value 3x higher than daytime P2P transfers."

The difference: the expected insight layers multiple data points (time window + type + network + baseline + amount comparison). The actual answer reports the single top row from a GROUP BY.

---

## Proposed Changes

### Change 1: Add "Multi-Step Analysis" guideline to the system prompt

**Where:** New section in `analyst_system.j2`, after `## Rules` and before `## Visualization`

**What to add:**

```
## Analysis Strategy

For complex questions that involve cross-referencing multiple dimensions
(e.g., time + transaction type + network), use multiple SQL queries to
build a layered analysis:

1. **Baseline first** -- compute the overall/average rate before segmenting.
   Always report segment metrics alongside the baseline for context
   (e.g., "4.5% vs the overall 0.8%").
2. **Drill progressively** -- start broad, then narrow. For example:
   first query gets overall failure rates by network, second query
   cross-references the worst networks with device types.
3. **Compare, don't just rank** -- reporting "the highest is X" is
   incomplete. Also report what the average is, what the lowest is,
   and what the magnitude of difference is.

You have up to 10 tool calls -- use multiple run_sql calls when a single
query cannot capture the full picture. A 3-query analysis that builds
context is better than a 1-query dump with 20 rows.
```

**Rationale:** This directly addresses gaps #1 and #2. The LLM has the iteration budget but doesn't know it should use it. This makes the multi-step pattern explicit.

### Change 2: Add domain-aware filtering rules to the system prompt

**Where:** Append to the existing `## Rules` section in `analyst_system.j2`

**What to add:**

```
9. **Transaction type scoping** -- apply appropriate filters based on what's being analyzed:
   - Bank-to-bank routing analysis (sender_bank -> receiver_bank) -> scope to
     `transaction_type = 'P2P'`, because only P2P transactions represent true
     inter-bank transfers.
   - Merchant category analysis (spending by category) -> scope to
     `transaction_type = 'P2M'`, because only P2M transactions occur at merchants.
   - If analyzing across all types, explicitly state that the results span
     all transaction types.
```

**Rationale:** Addresses gap #3. These are domain facts that the LLM can't infer from the schema alone. The Business Context doc describes the column values but doesn't encode these scoping rules.

### Change 3: Strengthen the Response Structure with comparative framing

**Where:** Modify the existing `## Response Structure` section in `analyst_system.j2`

**Current:**
```
2. **Supporting Evidence** (key numbers, comparisons, rankings from the data)
```

**Change to:**
```
2. **Supporting Evidence** (key numbers with baseline context -- always state
   both the segment value AND the overall/average for comparison, e.g.,
   "WiFi failure rate is 11.2% vs the overall 5.4%")
```

**Rationale:** Addresses gap #2 at the output level. Even if the analyst runs a single query, this forces it to include baseline context in the narrative.

### Change 4: Add a multi-step training example to `training/queries.py`

**Where:** Add 1-2 new entries to `EXAMPLE_QUERIES` that demonstrate multi-query analysis

**What to add:**

```python
{
    "category": "Multi-Step Analysis",
    "question": "Are there specific times when transactions are disproportionately "
                "flagged for review, and does this correlate with transaction types?",
    "sql": (
        "-- Step 1: Baseline flag rate\n"
        "SELECT COUNT(*) AS total_txns, "
        "SUM(fraud_flag) * 100.0 / COUNT(*) AS baseline_flag_rate_pct "
        "FROM transactions;\n\n"
        "-- Step 2: Flag rate by time window and transaction type\n"
        "SELECT "
        "CASE WHEN is_weekend = 1 AND hour_of_day IN (22,23,0,1,2,3) "
        "  THEN 'Weekend Late Night' "
        "WHEN is_weekend = 1 THEN 'Weekend Daytime' "
        "WHEN hour_of_day IN (22,23,0,1,2,3) THEN 'Weekday Late Night' "
        "ELSE 'Weekday Daytime' END AS time_window, "
        "transaction_type, "
        "COUNT(*) AS total_txns, "
        "SUM(fraud_flag) * 100.0 / COUNT(*) AS flag_rate_pct "
        "FROM transactions "
        "GROUP BY time_window, transaction_type "
        "ORDER BY flag_rate_pct DESC;"
    ),
},
```

**Important caveat:** The RAG auto-save stores question->SQL pairs. A multi-step example with two SQL statements in one string may confuse the RAG retrieval. Instead of embedding both queries in one `sql` field, consider this as a **prompt-level** example (in the system prompt) rather than a RAG training pair.

**Alternative approach:** Instead of modifying `training/queries.py`, add an inline example in the system prompt under the new `## Analysis Strategy` section:

```
Example -- "Are failure rates higher on 3G?"
  Query 1: SELECT ... overall failure rate -> 5.4%
  Query 2: SELECT ... failure rate by network_type -> 3G is 11.2%
  Answer: "3G transactions fail at 11.2%, more than double the overall 5.4%."
```

This avoids RAG complications and gives the LLM a concrete multi-step pattern to follow.

### Change 5: Enrich `training/documentation.py` with domain rules (optional)

**Where:** Add a new subsection to the `DOCUMENTATION` string in `training/documentation.py`

**What to add:**

```
### Transaction Type Semantics
- P2P (Person-to-Person): Inter-bank transfers between individuals.
  Both sender_bank and receiver_bank are meaningful.
  merchant_category is not applicable.
- P2M (Person-to-Merchant): Payments at merchant establishments.
  merchant_category is meaningful.
  receiver_bank represents the merchant's bank.
- Bill Payment: Utility and service bill payments.
- Recharge: Mobile/DTH recharges.
```

**Rationale:** Supplements Change 2 by embedding the domain knowledge in the business context that's injected into every prompt. Even if the system prompt rules are missed, this context will guide correct scoping.

---

## Changes NOT Proposed

1. **Increasing `max_agent_iterations`** -- Already at 10, which is plenty. The issue is that the LLM doesn't use multiple iterations, not that it runs out.

2. **Modifying `analyst.py` (the agentic loop code)** -- The loop logic is correct. It already supports multi-turn tool calls. The fix is in the prompt, not the code.

3. **Adding new tools** -- The existing `run_sql`, `get_schema`, `search_similar` toolset is sufficient. A dedicated "compute_baseline" tool would over-engineer what should be a second SQL call.

4. **Changing the guard rail** -- The "force tool use on first iteration" guard is good. No changes needed.

---

## Implementation Priority

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| P0 | Change 1: Multi-step analysis guideline | Small (add ~15 lines to .j2) | High -- directly fixes single-query habit |
| P0 | Change 2: Domain-aware filtering rules | Small (add ~5 lines to .j2) | High -- fixes incorrect scoping on Q3, Q4 |
| P1 | Change 3: Comparative framing in response | Tiny (edit 2 lines in .j2) | Medium -- improves output quality |
| P1 | Change 5: Transaction type semantics in docs | Small (add ~10 lines to documentation.py) | Medium -- reinforces Change 2 |
| P2 | Change 4: Multi-step training example | Medium (prompt design + testing) | Medium -- reinforces Change 1 via few-shot |

All changes are prompt-only -- no code changes to `analyst.py` or the agentic loop.

---

## Verification Plan

After implementing changes, re-run the same 4 questions via:

```bash
curl -s -X POST http://localhost:8000/api/chat/answer \
  -H 'Content-Type: application/json' \
  -b cookies.txt \
  -d '{"message": "...", "agent_mode": "analyst", "skip_clarification": true}'
```

**Pass criteria per question:**

| # | Question | Must Include |
|---|----------|-------------|
| Q1 | Fraud flag timing | Baseline flag rate + weekend vs weekday comparison + at least 2 SQL queries |
| Q2 | Network/device failure | Overall failure rate baseline + "X% vs overall Y%" framing |
| Q3 | Bank-to-bank routing | `WHERE transaction_type = 'P2P'` in the SQL |
| Q4 | Generational spending | `WHERE transaction_type = 'P2M'` in the SQL + frequency AND ticket size |
