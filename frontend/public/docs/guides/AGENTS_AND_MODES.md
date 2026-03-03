# InsightXpert: Agents, Modes & Orchestration

This document describes every agent, analysis mode, and orchestration pipeline in InsightXpert — what each component does, when it fires, why it exists, and what types of questions suit each mode.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Analysis Modes](#analysis-modes)
   - [Basic Mode](#basic-mode)
   - [Agentic Mode](#agentic-mode-default)
   - [Deep Think Mode](#deep-think-mode)
   - [Mode Selection Guide](#mode-selection-guide)
3. [Agents](#agents)
   - [SQL Analyst](#1-sql-analyst)
   - [Clarifier](#2-clarifier)
   - [Enrichment Evaluator](#3-enrichment-evaluator)
   - [Quant Analyst](#4-quant-analyst)
   - [Response Synthesizer](#5-response-synthesizer)
   - [Dimension Extractor](#6-dimension-extractor-deep-think-only)
   - [Deep Synthesizer](#7-deep-synthesizer-deep-think-only)
   - [Investigation Evaluator](#8-investigation-evaluator-deep-think-only)
   - [Investigation Synthesizer](#9-investigation-synthesizer-deep-think-only)
   - [Insight Quality Evaluator](#10-insight-quality-evaluator)
4. [Orchestration Pipelines](#orchestration-pipelines)
5. [Supporting Infrastructure](#supporting-infrastructure)
6. [Prompt Templates](#prompt-templates)
7. [Error Handling & Fallbacks](#error-handling--fallbacks)

---

## Architecture Overview

InsightXpert is a **multi-agent, analyst-first** system. Every question always starts with the SQL Analyst — the user gets a direct answer fast. Depending on the selected mode, additional agents may kick in to enrich, contextualize, and synthesize a deeper insight.

> **Visual diagram:** Open [`docs/diagrams/agentic-loop.excalidraw`](diagrams/agentic-loop.excalidraw) in [Excalidraw](https://excalidraw.com) for an interactive diagram of the agentic processing pipeline, showing Phase 1 (tool-calling loop), Phase 2 (enrichment evaluation and DAG execution), and Phase 3 (response synthesis and quality gate).

```
User Question
  │
  ├─ [Optional] Clarifier ── ambiguous? ask user first
  │
  ├─ SQL Analyst ──────────── always runs, user sees results immediately
  │
  ├─ [Agentic/Deep] Enrichment pipeline
  │   ├─ Evaluator / Dimension Extractor ── decides WHAT to investigate
  │   ├─ DAG Executor ── runs sub-tasks (SQL Analyst / Quant Analyst)
  │   └─ Synthesizer ── combines all evidence into cited insight
  │
  └─ [Deep only] Auto-Investigation ── finds gaps, runs follow-ups, re-synthesizes
```

**Key principle:** The system is designed so the user always gets a fast initial answer. Enrichment happens _after_ — the user sees the analyst's SQL and results while deeper analysis runs in the background.

---

## Analysis Modes

### Basic Mode

**API value:** `agent_mode="basic"`

```
Question → SQL Analyst → Answer → Done
```

**What it does:** Runs the SQL Analyst once. No enrichment, no orchestration, no synthesis. The analyst generates SQL, executes it, and returns the answer.

**Best for:**
- Simple factual lookups: _"How many transactions happened in Maharashtra?"_
- Single-metric queries: _"What's the average transaction amount?"_
- Quick counts and aggregations: _"Top 5 states by transaction volume"_
- When you already know the answer is in one query
- Speed-sensitive scenarios where you just need the number

**Not ideal for:**
- "Why" questions (no root-cause analysis)
- Questions that need context ("Is this high or low?")
- Multi-dimensional analysis

**Value:** Fast, cheap (1 LLM call + 1 SQL query), no overhead.

---

### Agentic Mode (Default)

**API value:** `agent_mode="agentic"`

```
Question
  → SQL Analyst (user sees results immediately)
    → Enrichment Evaluator (should we dig deeper?)
      → [If yes] DAG execution (1-4 parallel sub-tasks)
        → Response Synthesizer (combine with citations)
          → Insight Quality Gate (worth saving?)
```

**What it does:** The analyst answers first. Then an evaluator LLM call decides if the answer would benefit from enrichment — comparative context, temporal trends, root-cause analysis, or segmentation breakdowns. If yes, it plans 1-4 targeted sub-tasks, executes them (possibly in parallel), and synthesizes everything into a cited response.

**Best for:**
- Analytical questions: _"What's driving UPI failures in Maharashtra?"_
- Comparative questions: _"How does Delhi compare to Mumbai in card usage?"_
- Trend questions: _"Is mobile wallet adoption growing?"_
- Questions where one SQL query answers the surface but not the "so what?"
- Day-to-day analytical work that benefits from automatic context

**Not ideal for:**
- Simple lookups (overhead of evaluator is wasted)
- Questions requiring structured dimensional coverage

**Value:** Balances speed with depth. The evaluator avoids unnecessary work — simple questions skip enrichment entirely. When enrichment fires, the synthesizer produces a cited, leadership-ready response with sources like `[[1]]`, `[[2]]`.

**Enrichment categories:**
| Category | When triggered | Example |
|----------|---------------|---------|
| `comparative_context` | Answer shows a metric without benchmarks | "Is 7.2% failure rate high?" → compare across states |
| `temporal_trend` | No time dimension in the answer | "What's the fraud rate?" → show trend over months |
| `root_cause` | Pattern observed but not explained | "Why is X high?" → correlations, breakdowns |
| `segmentation` | Single aggregate without demographic cuts | "Average amount" → break by age, gender, city tier |

---

### Deep Think Mode

**API value:** `agent_mode="deep"`

```
Question
  → Dimension Extractor (5W1H mapping + enrichment planning)
    → SQL Analyst (user sees results)
      → DAG execution (pre-planned enrichment tasks)
        → Deep Synthesizer (dimensionally-structured response)
          → Insight Quality Gate
            → Auto-Investigation Evaluator (any gaps?)
              → [If yes] Follow-up task execution
                → Investigation Re-synthesizer (final insight)
```

**What it does:** The most thorough mode. Before the analyst even runs, a Dimension Extractor maps the question onto a **5W1H framework** (WHO, WHAT, WHEN, WHERE, HOW, WHY) and identifies which dimensions are covered, implicit, or missing. It pre-plans enrichment tasks to fill gaps. After the analyst answers and enrichment runs, a Deep Synthesizer structures the response by dimension. Then an auto-investigation phase checks for remaining gaps and runs follow-up queries without waiting for the user to ask.

**Best for:**
- Open-ended analytical questions: _"Analyze fraud patterns in India"_
- Executive-level questions: _"What are the key risk factors in our transaction data?"_
- Research-style deep dives: _"Explain the relationship between demographics and payment preferences"_
- Questions where you want comprehensive dimensional coverage
- When you're willing to wait for thoroughness

**Not ideal for:**
- Quick lookups (significant overhead)
- Time-sensitive answers
- Questions with a single obvious answer

**Value:** Produces the most comprehensive analysis. The 5W1H framework ensures no important dimension is missed. Auto-investigation means the system proactively fills gaps instead of waiting for the user to ask follow-ups. Output is structured by dimension with full citations.

**The 5W1H Framework:**
| Dimension | What it covers | Example |
|-----------|---------------|---------|
| **WHO** | Senders, receivers, demographics, segments | Which age groups are most affected? |
| **WHAT** | Core metric, magnitude, distribution | What's the fraud rate? How is it distributed? |
| **WHEN** | Temporal patterns, trends, seasonality | Is it increasing? Any seasonal spikes? |
| **WHERE** | Geographic distribution, regional patterns | Which states/cities are hotspots? |
| **HOW** | Payment channels, device types, mechanisms | Which payment method has highest risk? |
| **WHY** | Root causes, correlations, causal hypotheses | What factors drive this pattern? |

---

### Mode Selection Guide

| Question Type | Recommended Mode | Why |
|--------------|-----------------|-----|
| _"How many UPI transactions?"_ | Basic | Single fact, one query |
| _"Average amount by state"_ | Basic | Direct aggregation |
| _"Top 10 merchants by volume"_ | Basic | Simple ranking |
| _"Why is failure rate high in Maharashtra?"_ | Agentic | Needs comparison + root cause |
| _"How does Delhi compare to Mumbai?"_ | Agentic | Comparative analysis |
| _"Is card fraud increasing?"_ | Agentic | Needs temporal trend enrichment |
| _"Analyze transaction patterns"_ | Deep | Open-ended, multi-dimensional |
| _"What are the key fraud risk factors?"_ | Deep | Needs WHO/WHAT/WHEN/WHERE/HOW |
| _"Give me a complete picture of UPI adoption"_ | Deep | Executive-level comprehensive analysis |
| _"Explain demographic payment preferences"_ | Deep | Cross-dimensional, research-style |

**Rule of thumb:**
- Know the exact number you want? → **Basic**
- Want the number + context? → **Agentic**
- Want a full investigation report? → **Deep**

---

## Agents

### 1. SQL Analyst

**File:** `agents/analyst.py`
**Prompt:** `prompts/analyst_system.j2`
**Used in:** All modes (always the first agent to run)

**What it does:**
The SQL Analyst is the core workhorse. It converts natural language into SQL, executes the query, and narrates the results. It runs an agentic tool loop — it can call tools iteratively until it has a complete answer.

**Tools available:**
| Tool | Purpose |
|------|---------|
| `run_sql` | Execute a SELECT query with optional visualization spec |
| `get_schema` | Inspect table DDL to verify column names |
| `search_similar` | Search RAG store for similar past Q&A pairs |
| `clarify` | Ask the user a clarifying question (only if clarification is enabled) |

**Pipeline:**
1. RAG retrieval — find up to 3 similar past Q&A pairs from the vector store
2. Prompt assembly — render `analyst_system.j2` with DDL, documentation, RAG hits, and optional stats context
3. Agentic tool loop — iteratively call LLM with tools until a final answer or max iterations
4. Guard rail — first iteration forces tool use (prevents hallucinated answers without SQL)
5. Auto-save — on success, save the (question, SQL) pair to RAG for future few-shot retrieval

**Value:** Ensures every answer is grounded in actual data. The RAG flywheel means the system gets better with usage — successful Q&A pairs become few-shot examples for future similar questions.

---

### 2. Clarifier

**File:** `agents/clarifier.py`
**Prompt:** Hardcoded `CLARIFICATION_SYSTEM_PROMPT` in the file
**Used in:** Agentic and Deep modes (when `clarification_enabled=True`)

**What it does:**
A lightweight, single-shot LLM call that runs _before_ the analyst. It checks whether the user's question is genuinely ambiguous — meaning multiple reasonable interpretations would produce very different SQL queries.

**Decision logic:**
- If clear → `{"action": "execute"}` → analyst proceeds normally
- If ambiguous → `{"action": "clarify", "question": "..."}` → user sees a clarification question

**Examples:**
| Question | Clarifier Decision | Reasoning |
|----------|-------------------|-----------|
| _"Show me the data"_ | Clarify: "Which metrics? Transaction counts, amounts, or failure rates?" | "data" has too many interpretations |
| _"Average transaction amount"_ | Execute | Clear intent, one obvious SQL |
| _"Compare the cities"_ | Clarify: "Which cities would you like to compare?" | No cities specified |
| _"UPI failure rate in Maharashtra"_ | Execute | Unambiguous |

**Value:** Prevents wasted compute on questions that would produce wrong results. By asking one targeted question upfront, we avoid running the entire analyst pipeline on a misunderstood question. Falls back to "execute" on any error — never blocks the user.

---

### 3. Enrichment Evaluator

**File:** `agents/orchestrator_planner.py` → `evaluate_for_enrichment()`
**Prompt:** `prompts/enrichment_evaluator.j2`
**Used in:** Agentic mode (Phase 2)

**What it does:**
After the analyst produces an answer, this evaluator decides: _"Is this answer sufficient, or would additional context make it significantly better?"_ If enrichment is needed, it plans 1-4 targeted sub-tasks with dependencies.

**Input:** The analyst's SQL, result rows, and narrative answer.

**Decision criteria:**

_When NOT to enrich:_
- Simple lookups that the analyst answered completely
- Questions where the analyst already provided comparative context
- Already comprehensive multi-faceted answers

_When to enrich:_
- A single metric without benchmarks (needs `comparative_context`)
- No temporal dimension (needs `temporal_trend`)
- Pattern observed but not explained (needs `root_cause`)
- Single aggregate without demographic breakdown (needs `segmentation`)
- Volume shown without normalizing by population/base (needs context)

**Output:** Either `{"enrich": false}` or a plan with 1-4 tasks specifying agent type (`sql_analyst` or `quant_analyst`), category, question, and dependencies.

**Value:** This is the intelligence layer that prevents unnecessary work. A simple "how many transactions?" skips enrichment entirely. A "why is failure rate high?" triggers targeted follow-up queries. The evaluator is biased slightly toward enriching — the thinking is that additional context improves most analytical questions.

---

### 4. Quant Analyst

**File:** `agents/quant_analyst.py`
**Prompt:** `prompts/quant_analyst_system.j2`
**Used in:** Agentic and Deep modes (as an enrichment sub-task)

**What it does:**
The Quant Analyst is a downstream statistical agent. It receives upstream SQL Analyst results and applies quantitative analysis that goes beyond what SQL can do — statistical tests, distribution fitting, correlation analysis, anomaly detection, and fraud risk scoring.

**Tools available (merged registry):**

_Statistical tools:_
| Tool | Purpose |
|------|---------|
| `compute_descriptive_stats` | Mean, median, std dev, skewness, kurtosis |
| `test_hypothesis` | Chi-squared, t-test, ANOVA, Mann-Whitney U |
| `compute_correlation` | Pearson/Spearman correlation coefficients |
| `fit_distribution` | Fit data to theoretical distributions |

_Advanced analytics tools (from `advanced_tools.py`):_
| Tool | Purpose |
|------|---------|
| `run_sql` | Execute queries for data retrieval |
| `run_python` | Execute Python code for custom analysis |
| `percentile_ranking` | Rank values within distributions |
| `concentration_index` | Measure market concentration (HHI/Gini) |
| `fraud_risk_score` | Multi-factor fraud risk assessment |
| `amount_anomalies` | Detect unusual transaction amounts |
| `temporal_clustering` | Find time-based patterns |
| `benfords_law_test` | Statistical fraud detection test |

**When it's invoked:** Only as a sub-task in the enrichment DAG, never directly. The enrichment evaluator or dimension extractor assigns a task to `quant_analyst` when the question requires statistical rigor beyond SQL aggregations.

**Value:** Brings genuine statistical rigor. Instead of the analyst saying "Maharashtra has a high fraud rate," the quant analyst can say "Maharashtra's fraud rate (4.8%) is significantly higher than the national average (3.2%), χ²=1847.3, p<0.001, with Android UPI as the primary driver (r=0.68)." The p-values, effect sizes, and confidence intervals add credibility to the analysis.

---

### 5. Response Synthesizer

**File:** `agents/response_generator.py`
**Prompt:** `prompts/response_generator.j2`
**Used in:** Agentic mode (Phase 4, after enrichment)

**What it does:**
Takes evidence from all sub-tasks (original analyst + enrichment agents) and synthesizes a single, cited response suitable for leadership consumption.

**Citation system:**
- Source `[[1]]` = original analyst answer
- Source `[[2]]`, `[[3]]`, etc. = enrichment sub-task results
- Each source has a label (e.g., "Comparative Context", "Root-Cause Analysis")

**Output structure:**
1. Direct answer to the question
2. Key evidence with citations
3. Contextual analysis
4. Root-cause hypothesis (if applicable)
5. Business recommendations with specific data thresholds
6. Suggested follow-up questions

**Value:** Turns raw multi-source data into a coherent narrative. Without synthesis, the user would see disconnected results from 3-4 separate queries. The synthesizer weaves them together with proper attribution, so the reader knows exactly which data point came from which analysis.

---

### 6. Dimension Extractor (Deep Think only)

**File:** `agents/deep_think.py` → `_extract_dimensions()`
**Prompt:** `prompts/dimension_extractor.j2`
**Used in:** Deep mode (Phase 1, before the analyst)

**What it does:**
Maps the user's question onto a 5W1H framework and identifies analytical gaps. For each dimension (WHO, WHAT, WHEN, WHERE, HOW), it determines whether the question explicitly covers it, implicitly needs it, or leaves it uncovered. It then pre-plans enrichment tasks to fill the gaps.

**Output:**
```json
{
  "dimensions": {
    "who":   {"status": "implicit", "detail": "senders flagged for fraud"},
    "what":  {"status": "covered",  "detail": "fraud rate metric"},
    "when":  {"status": "uncovered","detail": "no temporal scope mentioned"},
    "where": {"status": "covered",  "detail": "Maharashtra explicitly asked"},
    "how":   {"status": "uncovered","detail": "payment type not addressed"}
  },
  "why_intent": "Root-cause analysis of fraud in a specific state",
  "suggested_enrichments": [
    {"id": "B", "agent": "sql_analyst", "category": "temporal_trend", "task": "..."},
    {"id": "C", "agent": "quant_analyst", "category": "root_cause", "task": "..."}
  ]
}
```

**Value:** This is what makes Deep Think fundamentally different from Agentic mode. Instead of reactively deciding "should we enrich?" after seeing the analyst's answer, the dimension extractor proactively identifies _what's missing from the question itself_. A question about "fraud in Maharashtra" might not mention time, payment type, or demographics — but a complete analysis needs all of those.

---

### 7. Deep Synthesizer (Deep Think only)

**File:** `agents/deep_think.py` → `_deep_synthesize()`
**Prompt:** `prompts/deep_synthesizer.j2`
**Used in:** Deep mode (Phase 4)

**What it does:**
Like the Response Synthesizer in agentic mode, but structures the output by 5W1H dimensions rather than as a flat narrative. Only includes dimensions that have supporting evidence.

**Output structure:**
1. **Direct Answer** — concise answer to the question
2. **WHO** — demographic/segment findings (if evidence exists)
3. **WHAT** — metric deep-dive with distributions
4. **WHEN** — temporal patterns and trends
5. **WHERE** — geographic distribution
6. **HOW** — channel/mechanism insights
7. **WHY** — root-cause hypothesis with causal reasoning
8. **Recommendations** — specific, data-cited action items
9. **Follow-up Questions** — what gaps remain

**Value:** The dimensional structure makes complex analyses scannable. A reader looking for geographic patterns goes straight to WHERE. Someone interested in trends goes to WHEN. This is especially valuable for executive audiences who want to jump to the dimension they care about.

---

### 8. Investigation Evaluator (Deep Think only)

**File:** `agents/orchestrator_planner.py` → `evaluate_for_investigation()`
**Prompt:** `prompts/investigation_evaluator.j2`
**Used in:** Deep mode (Phase 5, auto-triggered after synthesis)

**What it does:**
After deep synthesis, this evaluator reads the synthesized insight and decides: _"Are there analytical gaps that follow-up queries could fill?"_ Unlike the enrichment evaluator (which runs in agentic mode and requires user action), this runs automatically.

**Gap detection criteria:**
- Pattern revealed but not explained
- Key comparison missing
- Anomaly mentioned but not investigated
- Temporal dimension glossed over
- Unnormalized comparisons (missing cohort sizes)
- Volume-value gap (counts shown without amounts, or vice versa)
- Cross-category blindspot

**Value:** This is what makes Deep Think feel like having a data analyst who doesn't stop at the first answer. If the synthesis says "Android has higher fraud" but doesn't explain _why_, the investigation evaluator will spawn a follow-up query to investigate device-specific factors. The user gets a more complete picture without having to think of follow-up questions themselves.

---

### 9. Investigation Synthesizer (Deep Think only)

**File:** `agents/deep_think.py` → `_investigation_synthesize()`
**Prompt:** `prompts/investigation_synthesizer.j2`
**Used in:** Deep mode (Phase 6, after investigation tasks complete)

**What it does:**
Integrates investigation findings into the prior synthesis. Focuses on _what changed_ — what the investigation revealed that wasn't known before — rather than re-narrating everything.

**Output structure:**
1. Updated direct answer
2. Key findings (what investigation revealed)
3. Investigation insights (what gaps were filled)
4. Updated root-cause hypothesis
5. Updated recommendations with new evidence
6. Remaining gaps

**Value:** Avoids the common AI problem of repeating itself. The investigation synthesizer specifically focuses on delta — new evidence that changes or deepens the picture. The result is a final insight that reflects the full chain of analysis without redundancy.

---

### 10. Insight Quality Evaluator

**File:** `agents/orchestrator_planner.py` → `evaluate_insight_quality()`
**Prompt:** `prompts/insight_quality_evaluator.j2`
**Used in:** Agentic and Deep modes (final gate before saving)

**What it does:**
Decides whether a synthesized response is a "genuine insight" worth saving to the insights table for future reference.

**Is an insight:**
- Non-obvious patterns discovered through multi-source analysis
- Meaningful comparisons with statistical backing
- Actionable recommendations grounded in specific data
- Root causes identified with supporting evidence

**Not an insight:**
- Verbose restatement of what the analyst already said
- Enrichment that added no new data (all tasks failed/returned same info)
- Trivial comparison (e.g., "state A has more than state B" when that was the question)
- Over-enriched simple lookups

**Value:** Prevents the insights table from filling up with noise. Only genuinely valuable multi-source analyses get persisted, keeping the insight library high-signal for future reference.

---

## Orchestration Pipelines

### Basic Mode Pipeline

```
orchestrator_loop(agent_mode="basic")
  │
  └─ analyst_loop(question)
       ├─ RAG retrieval (similar past Q&A)
       ├─ Render analyst_system.j2
       ├─ Agentic tool loop (run_sql, get_schema, etc.)
       └─ Yield: sql chunk, tool_result chunk, answer chunk
```

**LLM calls:** 1 (analyst)
**Latency:** ~3-8 seconds

---

### Agentic Mode Pipeline

```
orchestrator_loop(agent_mode="agentic")
  │
  ├─ [Optional] clarification_check(question)
  │    └─ If ambiguous: yield clarification chunk, return
  │
  ├─ Phase 1: analyst_loop(question)
  │    └─ Yield: sql, tool_result, answer (user sees immediately)
  │
  ├─ Phase 2: evaluate_for_enrichment(question, analyst_sql, analyst_rows, analyst_answer)
  │    └─ If no enrichment needed: return (analyst answer stands)
  │
  ├─ Phase 3: execute_dag(enrichment_tasks)
  │    ├─ Task B (sql_analyst or quant_analyst) ─┐
  │    ├─ Task C (sql_analyst or quant_analyst) ─┤─ parallel where possible
  │    └─ Task D (quant_analyst, depends on B) ──┘─ sequential if dependency
  │    └─ Yield: agent_trace chunks for each task
  │
  ├─ Phase 4: generate_response(question, all_evidence)
  │    └─ Yield: insight chunk with citations
  │
  └─ Phase 5: evaluate_insight_quality(synthesized_response)
       └─ If genuine insight: flag for persistence
```

**LLM calls:** 2-8 (analyst + evaluator + 1-4 sub-tasks + synthesizer + quality gate)
**Latency:** ~10-30 seconds

---

### Deep Think Pipeline

```
deep_think_loop(agent_mode="deep")
  │
  ├─ Phase 1: _extract_dimensions(question)
  │    └─ 5W1H mapping + pre-planned enrichment tasks
  │
  ├─ Phase 2: analyst_loop(question)
  │    └─ Yield: sql, tool_result, answer (user sees immediately)
  │
  ├─ Phase 3: execute_dag(dimension_enrichment_tasks)
  │    └─ Yield: agent_trace chunks
  │
  ├─ Phase 4: _deep_synthesize(all_evidence, dimensions)
  │    └─ Yield: insight chunk (5W1H-structured)
  │
  ├─ Phase 5: evaluate_insight_quality(synthesis)
  │    └─ Flag for persistence if genuine
  │
  ├─ Phase 6: evaluate_for_investigation(synthesis)
  │    └─ If no gaps: return
  │
  ├─ Phase 7: execute_dag(investigation_tasks)
  │    └─ Yield: agent_trace chunks
  │
  └─ Phase 8: _investigation_synthesize(prior_synthesis, new_evidence)
       └─ Yield: updated insight chunk
```

**LLM calls:** 4-12 (extractor + analyst + 1-4 enrichment + synthesizer + quality gate + investigation evaluator + 1-2 follow-ups + re-synthesizer)
**Latency:** ~20-60 seconds

---

## Supporting Infrastructure

### RAG (Retrieval-Augmented Generation)

When the analyst successfully generates SQL, the (question, SQL) pair is automatically saved to a ChromaDB vector store. On future questions, similar past pairs are retrieved and injected as few-shot examples. This creates a **flywheel** — more usage means better future answers.

### DAG Executor

`agents/dag_executor.py` handles parallel execution of sub-tasks with dependency tracking. Tasks without dependencies run concurrently. Tasks with `depends_on` wait for their predecessors. The executor handles timeouts, errors, and result aggregation.

### Stats Context Injection

When enabled (`stats_context_injection=True`), pre-computed dataset statistics are injected into the analyst prompt. The analyst can answer certain questions directly from stats without running SQL (e.g., "What's the average transaction amount by age group?" if already pre-computed).

### Feature Toggles

Per-organization toggles control:
- `clarification_enabled` — whether the clarifier runs
- `stats_context_injection` — whether pre-computed stats are injected
- `rag_retrieval` — whether RAG lookup is used

---

## Prompt Templates

All prompts live in `backend/src/insightxpert/prompts/` as Jinja2 templates. They support DB-first resolution (admin can override via `prompt_templates` table) with file fallback.

| Template | Agent | Key Variables |
|----------|-------|--------------|
| `analyst_system.j2` | SQL Analyst | `ddl`, `documentation`, `similar_qa`, `stats_context`, `clarification_enabled` |
| `enrichment_evaluator.j2` | Enrichment Evaluator | `question`, `analyst_sql`, `analyst_rows`, `analyst_answer`, `history` |
| `orchestrator_planner.j2` | Orchestrator Planner (legacy) | `ddl`, `documentation`, `rag_context`, `max_tasks` |
| `quant_analyst_system.j2` | Quant Analyst | `ddl`, `documentation`, `upstream_context`, `analyst_sql`, `results_summary` |
| `response_generator.j2` | Response Synthesizer | `question`, `evidence_data`, `plan_reasoning` |
| `dimension_extractor.j2` | Dimension Extractor | `ddl`, `documentation`, `question`, `history` |
| `deep_synthesizer.j2` | Deep Synthesizer | `question`, `evidence_data`, `dimensions_summary`, `why_intent` |
| `investigation_evaluator.j2` | Investigation Evaluator | `question`, `analyst_sql`, `synthesized_insight`, `enrichment_evidence` |
| `investigation_synthesizer.j2` | Investigation Synthesizer | `question`, `prior_synthesis`, `prior_evidence`, `new_evidence` |
| `insight_quality_evaluator.j2` | Insight Quality Evaluator | `question`, `synthesized_content`, `enrichment_task_count` |

---

## Error Handling & Fallbacks

Every component degrades gracefully:

| Component | On Failure | Behavior |
|-----------|-----------|----------|
| RAG retrieval | Warning logged | Analyst proceeds without few-shot examples |
| Stats context | Warning logged | Analyst forced to run SQL |
| Clarifier | Warning logged | Proceeds to analyst (no clarification) |
| Enrichment evaluator | Warning logged | Analyst answer stands (no enrichment) |
| Quant analyst sub-task | Task marked "error" | Synthesis uses available results, skips failed task |
| Response synthesis | Falls back | Returns concatenated agent answers |
| Insight quality check | Default | Saves as insight (`is_insight=True`) |
| Investigation evaluator | Warning logged | Prior synthesis stands unchanged |
| Dimension extraction | Warning logged | Falls back to agentic-mode pipeline |

**Timeouts:**
| Component | Timeout |
|-----------|---------|
| Enrichment evaluator | 60 seconds |
| Investigation evaluator | 30 seconds |
| Insight quality evaluator | 15 seconds |
| Dimension extraction | 15 seconds |
| Synthesizers | 60 seconds |
