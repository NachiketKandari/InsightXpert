# InsightXpert Agent Pipeline

InsightXpert's AI pipeline converts a natural-language question into an evidence-backed answer by orchestrating LLM calls, SQL execution, vector store retrieval, and optional statistical sub-agents. This document covers every phase of the pipeline from the initial request to the final SSE chunk.

---

## Overview

The pipeline operates in three modes selected by the `agent_mode` field of `ChatRequest`:

| Mode | Description |
|---|---|
| `basic` (formerly `analyst`) | Single SQL analyst loop. Direct question → SQL → answer. |
| `agentic` (formerly `auto`, `statistician`, `advanced`) | Analyst-first with conditional enrichment via a multi-agent DAG. |
| `deep` | 5W1H dimensional analysis: extracts WHO/WHAT/WHEN/WHERE/HOW dimensions, runs analyst, executes targeted enrichment, synthesizes a structured insight. |

Legacy mode names (`auto`, `statistician`, `advanced`, `analyst`) are mapped in `api/models.py` via `_LEGACY_MODE_MAP` and in `orchestrator_loop()` before dispatch.

---

## Entry Point

`POST /api/chat` is handled by `chat_sse()` in `api/routes.py`. Before any agent logic runs, `_prepare_chat()` executes:

1. Retrieves `llm`, `db`, `rag`, `settings`, `conv_store`, `dataset_service` from `app.state`
2. Gets in-memory history for the conversation ID
3. If in-memory history is empty but a `conversation_id` was provided, hydrates from `PersistentConversationStore` (handles server restarts and TTL expiry)
4. Adds the user message to in-memory store
5. Ensures a `conversations` row exists in SQLite via `get_or_create_conversation`
6. Persists the user message to SQLite

A `_TokenCountingLLM` wrapper is created around the base LLM provider to accumulate `input_tokens` and `output_tokens` across all LLM calls in the request.

Feature flags are resolved via `_resolve_user_features(request, user)`:
- Reads `ClientConfig` from DB (60s TTL cache)
- Determines the user's org from `user_org_mappings`
- Returns the org-specific `FeatureToggles` (or global defaults for admins and admin-domain users)

`orchestrator_loop()` is then called as an async generator, and each yielded `ChatChunk` is serialized to JSON and sent as an SSE event.

---

## Stats Context Pre-Fetch

Before the analyst runs, `orchestrator_loop()` resolves pre-computed stats if the `stats_context_injection` feature flag is ON:

```python
if config.enable_stats_context and stats_context_injection:
    stats_result = await asyncio.to_thread(StatsResolver().resolve, question, db.engine)
    if stats_result:
        stats_context = stats_result.markdown
        stats_groups = stats_result.groups
```

`StatsResolver.resolve()` lowercases the question and scans `STAT_PATTERNS` — a list of `(keyword_list, stat_group_list)` tuples. If any keyword matches, it queries the `dataset_stats` table for those groups and formats the results as compact markdown. Example patterns:

- Keywords `["bank", "sbi", "hdfc", ...]` → fetch stat group `"bank"`
- Keywords `["fraud", "flag", "flagged", ...]` → fetch groups `["overall", "merchant_category", "state"]`
- Keywords `["month", "monthly", "trend", ...]` → fetch group `"monthly"`

The resolved markdown is passed into `analyst_loop()` as `stats_context`. If no keywords match, `stats_context` remains `None` and there is no performance overhead.

---

## Active Dataset Resolution

`orchestrator_loop()` resolves the active dataset's DDL and documentation before running any agent:

```python
active_ds = await asyncio.to_thread(dataset_service.get_active_dataset)
if active_ds:
    ddl_override = active_ds.get("ddl")
    docs_override = await asyncio.to_thread(
        dataset_service.build_documentation_markdown, active_ds["id"]
    )
```

If an active dataset exists, `ddl_override` and `docs_override` replace the hardcoded `training/schema.py` DDL and `training/documentation.py` documentation throughout the entire pipeline (analyst, quant analyst, response generator). This enables the multi-tenant dataset feature.

---

## Basic Mode: analyst_loop

`analyst_loop()` in `agents/analyst.py` is an async generator that yields `ChatChunk` objects. The caller iterates over them and either yields them downstream (agentic mode) or streams them directly to the SSE response (basic mode).

### Step 1 — RAG Retrieval

```python
similar_qa = await asyncio.to_thread(
    rag.search_qa, question, n=5, max_distance=1.0, sql_valid_only=True,
)
```

Fetches up to 5 question→SQL pairs from ChromaDB that:
- Are semantically similar to the question (L2 distance ≤ 1.0)
- Were previously validated (`sql_valid=True` in metadata)

These pairs become few-shot examples in the system prompt. The distance threshold of 1.0 filters weak matches that would add noise. RAG retrieval latency is logged in milliseconds.

A `status` chunk is yielded with the count of matches found and the question titles for the frontend's RAG context dropdown.

### Step 2 — System Prompt Assembly

```python
system_prompt = render_prompt(
    "analyst_system.j2",
    engine=db.engine,
    ddl=active_ddl,
    documentation=active_docs,
    similar_qa=similar_qa,
    relevant_findings=[],
    stats_context=stats_context,
    clarification_enabled=clarification_enabled,
)
```

`render_prompt()` tries the DB first (`prompt_templates` table), falls back to the `.j2` file. The Jinja2 template conditionally includes:
- DDL section (always)
- Documentation section (always)
- `{% if similar_qa %}` — few-shot example block
- `{% if stats_context %}` — pre-computed statistics block with instructions to answer from stats when sufficient
- `{% if clarification_enabled %}` — instructions for when to use the `clarify` tool

If `stats_context` was injected but the DB template predates the stats feature (no `stats_context` block), the stats are appended directly to the system prompt as a fallback.

### Step 3 — Message List Assembly

```python
messages = [
    {"role": "system", "content": system_prompt},
    # conversation history (prior user/assistant turns, max 20)
    *history,
    {"role": "user", "content": question},
]
```

History messages are injected between the system prompt and the current question. This gives the LLM conversational context for multi-turn follow-up questions.

### Step 4 — Agentic Tool Loop

The loop runs up to `max_agent_iterations` (default 10) iterations:

```python
for iteration in range(max_iter):
    response = await llm.chat(messages, tools=tool_registry.get_schemas())
    ...
```

**Guard rail — force tool use (first iteration):**

If `response.tool_calls` is empty AND no tools have been executed yet in this session:

- If `stats_context` is present: the LLM is permitted to answer directly from stats. A `stats_context` chunk is emitted for frontend transparency, then execution falls through to the final-answer branch.
- Otherwise: the response is rejected. The LLM's partial answer is appended to messages as an assistant message, followed by a corrective user message:

  ```
  "You MUST use the run_sql tool to query the database before answering.
  Do not answer from memory or prior context."
  ```

  (When `clarification_enabled=True`, the corrective message also allows the `clarify` tool.)

  The loop continues to the next iteration.

This guard prevents the LLM from hallucinating answers based on training data or the few-shot examples in the prompt. Every answer must be backed by a database query unless pre-computed stats are sufficient.

**When tool calls are present:**

For each `ToolCall` in `response.tool_calls`:

1. Yield a `tool_call` chunk (tool name, arguments, optional LLM reasoning from `response.content`)
2. If the tool is `run_sql`: yield a `sql` chunk with the query text and a `status` chunk
3. Execute the tool: `await tool_registry.execute(tc.name, tc.arguments, tool_context)`
4. Set `tools_executed = True`
5. If the tool is `clarify`: parse the JSON result, yield a `clarification` chunk, and `return` (stop the loop — wait for the user's answer)
6. Append the tool result to messages as a `{"role": "tool", ...}` message
7. Yield a `tool_result` chunk (includes `visualization`, `x_column`, `y_column` hints for chart rendering)

The loop continues. The LLM receives tool results and generates another response.

**When no tool calls after tools have executed:**

The LLM has produced a final text answer. Yield an `answer` chunk with `response.content` and break.

**Iteration exhaustion:**

If all `max_iter` iterations complete without a final answer, yield an `error` chunk and stop.

### Step 5 — Auto-Save

After a successful answer, `_extract_sql_from_messages()` walks the message list in reverse to find the last SQL (from a `run_sql` tool call argument or a fenced ` ```sql ``` ` block in any message). The pair is persisted:

```python
await asyncio.to_thread(
    rag.add_qa_pair, question, sql, {"sql_valid": True},
)
```

This creates a self-improving flywheel: every successful answer becomes a future few-shot example. Auto-save failures are logged at DEBUG level and do not affect the response.

---

## Agentic Mode: orchestrator_loop

`orchestrator_loop()` in `agents/orchestrator.py` implements the four-phase analyst-first enrichment flow.

### Phase 1 — Analyst (Immediate Results)

The analyst runs with the original question. Every chunk is yielded directly to the SSE response — the user sees SQL, table results, and the answer immediately, before any enrichment begins.

Simultaneously, the orchestrator collects:
- `analyst_sql` — extracted from `sql` chunks
- `analyst_rows` — parsed from `tool_result` chunks where `tool == "run_sql"` (up to the full result set)
- `analyst_answer` — extracted from `answer` chunks
- `analyst_had_error` — set if any `error` or `clarification` chunk is emitted

If the analyst had an error or produced no answer, the orchestrator stops here and returns. No enrichment is attempted.

### Phase 2 — Enrichment Evaluation

A `status` chunk announces that deeper analysis is being evaluated.

RAG context for the evaluator is fetched:
```python
similar = rag.search_qa(question, n=5)
rag_context = [doc for doc if doc["distance"] <= 1.0]
```

Then `evaluate_for_enrichment()` is called (timeout: 60 seconds):

```python
enrichment_plan = await evaluate_for_enrichment(
    question=question,
    analyst_sql=analyst_sql,
    analyst_rows=analyst_rows,
    analyst_answer=analyst_answer,
    llm=llm,
    ddl=effective_ddl,
    documentation=effective_docs,
    history=history,
    rag_context=rag_context,
    max_tasks=config.max_orchestrator_tasks,
)
```

Inside `evaluate_for_enrichment()`:
1. Renders `enrichment_evaluator.j2` with all context (question, SQL, rows summary, answer, RAG hits, history)
2. Single LLM call with no tools — output must be JSON
3. If `parsed["enrich"] == False`: returns `None` → analyst answer stands, no enrichment
4. If `parsed["enrich"] == True`: validates the task plan via `_validate_plan()` and returns an `OrchestratorPlan`

The evaluator prompt biases toward "no enrichment" for simple factual questions and toward "yes" for questions where comparative context, temporal trends, root-cause analysis, or segmentation would materially improve the answer.

On any failure (timeout, JSON parse error, validation error), `evaluate_for_enrichment()` returns `None` — the analyst answer stands.

### Phase 3 — DAG Execution

An `orchestrator_plan` chunk is emitted listing the enrichment tasks.

`execute_dag()` in `agents/dag_executor.py` runs tasks with maximum parallelism:

```python
results = await execute_dag(
    plan=enrichment_plan,
    run_task=run_task,
    on_task_start=on_task_start,
    on_task_complete=on_task_complete,
)
```

The DAG executor:
1. Finds all tasks whose `depends_on` list is empty or fully satisfied
2. Launches them all concurrently with `asyncio.gather()`
3. As tasks complete, checks for newly unblocked tasks and launches those
4. Repeats until all tasks are done, errored, or skipped
5. On task failure: marks downstream tasks as `skipped` recursively

Circular dependencies are detected at validation time via Kahn's algorithm (`_has_cycle()`). If a cycle is found, all dependency links are removed and tasks run in parallel.

Each task runs as either:

**`sql_analyst`** — calls `analyst_loop()` for the sub-task's natural-language question. Collects `collected_sql`, `collected_rows`, `collected_answer`, and full `trace_steps` (one step per chunk). Returns a `SubTaskResult`.

**`quant_analyst`** — calls `quant_analyst_loop()` with `upstream_results` (the `SubTaskResult` from depended-on tasks). The quant analyst merges upstream rows into a DataFrame and runs statistical analysis tools. Returns a `SubTaskResult` with an `answer` but typically no `sql`.

`on_task_start` and `on_task_complete` callbacks accumulate `status` and `agent_trace` chunks in `pending_chunks`, which are yielded after the DAG completes.

### Sub-Task Categories

The evaluator assigns each task one of four categories:

| Category | Label | When used |
|---|---|---|
| `comparative_context` | Comparative Context | Question asks about a specific value but benchmark context is missing |
| `temporal_trend` | Temporal Trend | Data changes over time and the analyst showed a snapshot |
| `root_cause` | Root-Cause Analysis | Anomaly or outlier in the analyst result needs explanation |
| `segmentation` | Segmentation | Aggregate answer would be more useful broken down by a dimension |

### Phase 4 — Response Synthesis

`generate_response()` in `agents/response_generator.py` makes a single LLM call (no tools) to combine all evidence into a cited response:

Evidence blocks are assembled:
- Source [1]: Original analyst answer (question, SQL, rows summary, answer)
- Source [2..N]: Each successful enrichment task (category label, task description, SQL, rows summary, answer)

The `response_generator.j2` template instructs the LLM to write a leadership-grade response with inline citations `[1]`, `[2]`, etc. matching the source indices.

The synthesized markdown is emitted as an `insight` chunk.

On LLM failure, `_fallback_answer()` concatenates individual agent answers separated by `---` dividers.

### Phase 5 — Enrichment Traces

After the insight, one `enrichment_trace` chunk is emitted per source for the citation system:

- Source [1]: Original analyst (category "SQL Analysis", question, sql, answer, no steps)
- Source [2..N]: Each successful enrichment task (category label, question, sql, answer, full trace_steps)

The frontend's `CitationLink` component renders `[N]` references in the insight text as clickable links. Clicking opens a `TraceModal` showing the source's category, question, SQL, and execution steps.

---

## Deep Think Mode

`deep_think_loop()` in `agents/deep_think.py` extends the agentic flow with a 5W1H framing:

**Phase 1 — Dimension Extraction** (15s timeout):
Single LLM call maps the question onto WHO/WHAT/WHEN/WHERE/HOW dimensions, identifies the WHY intent, and pre-plans targeted enrichment tasks for any uncovered dimensions.

**Phase 2 — Analyst**:
`analyst_loop()` runs unchanged. User sees immediate results.

**Phase 3 — Targeted Enrichment**:
The pre-planned enrichment tasks from Phase 1 execute via `execute_dag()`, reusing `_run_sql_analyst()`.

**Phase 4 — Synthesis** (60s timeout):
`deep_synthesizer.j2` template produces a 5W1H-structured insight with `[[N]]` citations.

---

## Quant Analyst Sub-Agent

`quant_analyst_loop()` in `agents/quant_analyst.py` is used for enrichment tasks that require statistical analysis beyond SQL.

### Setup

Upstream results from depended-on `sql_analyst` tasks are merged:
```python
for task_id, result in upstream_results.items():
    if result.success and result.rows:
        merged_results.extend(result.rows)
```

A `ToolContext` is created with `analyst_results=merged_results` so all stat tools have access to the upstream DataFrame.

If no upstream data is available, the agent emits an `error` chunk and returns immediately.

### System Prompt

`quant_analyst_system.j2` receives:
- DDL and documentation (same as analyst)
- `analyst_sql` — the SQL that produced the upstream data
- `results_summary` — compact text summary of upstream rows
- `upstream_context` — per-source markdown blocks with source ID, SQL, row count, and answer excerpt

### Tool Loop

`agent_tool_loop()` in `agents/common.py` runs the agentic loop (same logic as the analyst loop, without the guard rail since the quant analyst always has data to work with). Max iterations: `max_quant_analyst_iterations` (default 5).

### Available Tools

The quant analyst's `_quant_registry()` merges the advanced registry (which includes `run_sql` and `run_python`) with the four stat-specific tools:

**`compute_descriptive_stats`**:
- Input: `{"column": "amount"}`
- Output: count, mean, std, min, Q1, median, Q3, max, skewness, kurtosis

**`test_hypothesis`**:
- Supported tests: `chi_squared`, `t_test`, `mann_whitney`, `anova`, `z_proportion`
- `chi_squared`: contingency table test with Cramér's V effect size
- `t_test`: Welch's t-test with Cohen's d
- `mann_whitney`: non-parametric U-test with rank-biserial r
- `anova`: one-way F-test with eta squared
- `z_proportion`: one-sample proportion test
- All tests report `significant_at_005: bool`

**`compute_correlation`**:
- Methods: `pearson`, `spearman`, `kendall`
- Reports coefficient, p-value, n, significance flag

**`fit_distribution`**:
- Candidates: normal, exponential, lognormal, gamma, weibull_min
- Ranked by KS-test p-value (higher = better fit)
- Reports params for each fitted distribution

**`run_python`** (sandboxed):
- Pre-loaded globals: `np`, `pd`, `stats` (scipy.stats), `math`, `json`, `itertools`, `collections`, `functools`, `datetime`, `re`, `df`
- Import whitelist: `_ALLOWED_IMPORT_ROOTS` — numpy, pandas, scipy, math, json, itertools, collections, functools, datetime, re, statistics, warnings, operator, string, textwrap, decimal, fractions, numbers, copy, enum, typing, io, csv, dataclasses, abc
- Timeout: `SIGALRM` on Unix (silently skipped on Windows or non-main threads)
- `df` sync-back: if the code modifies `df`, the modified DataFrame is written back to `context.analyst_results` so subsequent tools see derived columns

**`run_sql`**: available for additional data fetching when the upstream data is insufficient.

---

## Guard Rails

### Force Tool Use

The analyst loop's most important guard: on the first iteration, if the LLM responds with text only (no tool calls) and no stats context was injected, the response is rejected. A corrective user message forces the LLM to call `run_sql`. This prevents the LLM from answering from its training data or the few-shot examples in the prompt instead of the actual database.

The force message differs based on `clarification_enabled`:
- With clarification: allows both `run_sql` and `clarify`
- Without: only `run_sql` is allowed

### SQL Blocklist

`POST /api/sql/execute` (the direct SQL endpoint) enforces a regex blocklist:

```python
_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA\s+\w+\s*=)\b",
    re.IGNORECASE,
)
```

Blocked queries return HTTP 403. The agent's `run_sql` tool does not apply this regex — it relies on the `PRAGMA query_only` enforcement in `DatabaseConnector.execute()`.

### Read-Only Enforcement

`DatabaseConnector.execute(read_only=True)` issues `PRAGMA query_only = ON` before the query and `PRAGMA query_only = OFF` in a `finally` block. Any attempt to write while `query_only` is ON raises a SQLite error. The agent's `run_sql` tool does not pass `read_only=True` explicitly — but the transactions table is append-only from the application's perspective, and all agent SQL is SELECT-only by instruction.

### Row Limits

`DatabaseConnector.execute(row_limit=N)` uses `fetchmany(N)` instead of `fetchall()`. The analyst uses `config.sql_row_limit` (default 10,000). Historical conversation chunks are truncated to 50 rows in `_truncate_chunks()` before sending to the frontend.

### Iteration Limits

- Analyst: `max_agent_iterations` (default 10)
- Quant analyst: `max_quant_analyst_iterations` (default 5)
- Enrichment tasks: `max_orchestrator_tasks` (default 5)
- Enrichment evaluator: 60-second timeout

### Sanitized Errors

`ToolRegistry.execute()` wraps every tool call in a try/except and returns `json.dumps({"error": str(e)})`. Python tracebacks are never sent to the LLM or the user — only the exception message string. The LLM receives sanitized error strings and can adjust its next tool call accordingly.

---

## Clarification System

The clarification system lets the LLM ask the user for more information when a question is ambiguous or references schema columns that don't exist.

### Activation

Enabled when `clarification_enabled=True` in the user's resolved `FeatureToggles` AND `skip_clarification=False` in the `ChatRequest`. The effective flag is:

```python
effective_clarification = clarification_enabled and not skip_clarification
```

When `effective_clarification=True`, `ClarifyTool` is added to the tool registry and included in the system prompt.

### Flow

1. LLM calls `clarify({"question": "Did you mean X or Y?"})` instead of `run_sql`
2. `ClarifyTool.execute()` returns `{"clarification": "..."}`
3. The analyst loop detects the `clarify` tool name, parses the result, emits a `clarification` chunk, and returns immediately
4. The frontend renders the clarification question with two options: answer it, or click "Just answer" (which sets `skip_clarification=true` in the next request)
5. If the user answers, their answer is appended to the question in the next request
6. If the user clicks "Just answer", `skip_clarification=true` disables `ClarifyTool` for that request and the LLM must answer directly

### Prompt Instruction

When `clarification_enabled=True`, `analyst_system.j2` includes a section instructing the LLM to use `clarify` when the question references a column or concept that doesn't exist in the schema, and to suggest the closest available alternative.

---

## Token Tracking

`_TokenCountingLLM` wraps the base LLM provider and accumulates token counts:

```python
async def chat(self, messages, tools=None):
    resp = await self._llm.chat(messages, tools)
    self.input_tokens += resp.input_tokens
    self.output_tokens += resp.output_tokens
    return resp
```

After all chunks are yielded and before `[DONE]`, a `metrics` chunk is emitted:

```python
metrics_chunk = ChatChunk(
    type="metrics",
    data={
        "input_tokens": counting_llm.input_tokens,
        "output_tokens": counting_llm.output_tokens,
        "generation_time_ms": generation_time_ms,
    },
    ...
)
```

`generation_time_ms` is the wall-clock time of the entire orchestrator loop (from before `orchestrator_loop()` was called to after the last chunk). This is the correct measure of end-to-end LLM processing time.

Token counts and `generation_time_ms` are stored in the `messages` table alongside the assistant message content.

---

## Conversation Persistence

### Fire-and-Forget Pattern

Persistence is intentionally asynchronous to keep SSE latency low:

```python
yield {"data": "[DONE]"}  # client stops spinner immediately

asyncio.ensure_future(
    asyncio.to_thread(
        _persist_response,
        conv_store, persistent_store, store_cid, persistent_cid, user.id,
        final_answer[-1] if final_answer else "",
        executed_sql,
        "[" + ",".join(all_chunks) + "]",
        counting_llm.input_tokens or None,
        counting_llm.output_tokens or None,
        generation_time_ms,
        org_id=user.org_id,
        question=chat_req.message,
    )
)
```

`[DONE]` is yielded before `asyncio.ensure_future()` is called, so the client's spinner stops as soon as the answer is delivered. The DB write happens after.

### `_persist_response()`

This synchronous function (called via `asyncio.to_thread`) performs several writes:

1. **In-memory store** — adds the assistant answer to `ConversationStore` (for future multi-turn context injection)
2. **Assistant message** — saves to `messages` table with full `chunks_blob` (JSON array of all SSE events), token counts, and generation time
3. **Enrichment traces** — parses `enrichment_trace` chunks from the blob and saves to `enrichment_traces` table
4. **Orchestrator plan** — parses `orchestrator_plan` chunk and saves to `orchestrator_plans` table
5. **Agent executions** — parses `agent_trace` chunks and saves to `agent_executions` table (linked to the plan)
6. **Insight** — parses `insight` chunk and saves to `insights` table with categories, summary, and enrichment task count

All writes are conditional: they only occur if the relevant chunk type is present in the blob. A conversation with a basic mode response will have no enrichment traces, orchestrator plan, or insight rows.

### History Injection

On subsequent turns, history is injected between the system prompt and the current question:

```python
messages = [
    {"role": "system", "content": system_prompt},
    *history,  # prior user+assistant turns (max 20)
    {"role": "user", "content": question},
]
```

The in-memory store holds condensed history — user messages and assistant final answers only. Tool call/result intermediaries are not stored in the history, keeping context window usage manageable. The max depth is `MAX_HISTORY_TURNS = 20` messages.

For sub-tasks in enrichment DAG execution, `history=None` is passed — sub-agents do not receive conversation history, only their specific task.

---

## SSE Consumer (Frontend)

The frontend's SSE client (`lib/sse-client.ts`) reads the streaming response:

1. Opens a `fetch()` with the request body, reads via `ReadableStream`
2. Parses SSE `data:` lines into `ChatChunk` objects
3. Dispatches each chunk to a callback
4. On `[DONE]`: closes the stream and signals completion

React 18's automatic batching means state updates from multiple consecutive chunks are batched into a single re-render. The drain loop processes all queued chunks synchronously:

```typescript
while (queue.length > 0) {
    const chunk = queue.shift();
    dispatchChunk(chunk);
}
```

`answer-chunk.tsx` is wrapped with `React.memo` to prevent markdown re-parsing when the answer content has not changed (e.g. when a later `metrics` chunk arrives).

Auto-scroll in `message-list.tsx` depends on `[messages.length, lastMsgChunkCount]` — it scrolls when a new message is added or when the chunk count for the last message increases, but not when feedback state changes on earlier messages.
