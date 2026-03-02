# InsightXpert — Architecture & Technical Vision

> **Note (Mar 2, 2026):** This document was the original technical blueprint written on Feb 17, 2026. Most of the "planned" features described here have since been fully implemented. For current, comprehensive documentation, see the `docs/` directory:
>
> - **[docs/architecture.md](docs/architecture.md)** — System architecture
> - **[docs/agent-pipeline.md](docs/agent-pipeline.md)** — Agent pipeline deep dive
> - **[docs/AGENTS_AND_MODES.md](docs/AGENTS_AND_MODES.md)** — Agent modes & orchestration
> - **[docs/agent-tools.md](docs/agent-tools.md)** — All 21 tools reference
> - **[docs/api-reference.md](docs/api-reference.md)** — Full API reference (50+ endpoints)
> - **[docs/automations.md](docs/automations.md)** — Automations system
> - **[docs/frontend.md](docs/frontend.md)** — Frontend architecture
> - **[docs/configuration.md](docs/configuration.md)** — Configuration reference
> - **[docs/contributing.md](docs/contributing.md)** — Contributing guide
> - **[docs/dataset.md](docs/dataset.md)** — Dataset documentation
> - **[WALKTHROUGH.md](WALKTHROUGH.md)** — Complete project walkthrough
>
> This file is preserved as a historical record of the original design vision and build plan.

## What This Document Is

This is the unified technical blueprint for InsightXpert — merging the Techfest PRD requirements, the from-scratch SQL agent engine, the multi-agent vision, and the observability/dashboard layer into a single coherent architecture. It defines what to build, why, and in what order to hit the Feb 28 submission and Mar 8 presentation.

---

## 1. Problem (from PRD)

Non-technical leadership at Indian fintech companies need to ask questions like:
- "Which merchant categories show the highest failure rates during peak hours?"
- "How do transaction patterns differ between age groups on weekends?"

...and get accurate, explainable answers backed by data — without writing SQL.

**Dataset:** 250K synthetic Indian digital payment transactions, 17 columns, single `transactions` table in SQLite.

**Evaluation weights:** Insight Accuracy (30%), Query Understanding (25%), Explainability (20%), Conversational Quality (15%), Innovation (10%).

---

## 2. Current State (as of Feb 17, updated Mar 2)

The from-scratch engine has replaced Vanna and is fully ported. The single-agent analyst pipeline is working end-to-end. The frontend chat UI with SSE streaming is fully implemented. Authentication, persistent conversations, runtime LLM switching, and a SQL executor are all operational. Three design patterns (LLM Factory, Tool ABC + Registry, VectorStore Protocol) formalize the extension points. Error handling wraps all LLM calls with proper error surfacing. Conversation persistence correctly bridges frontend-generated IDs with backend storage via `get_or_create_conversation`. Message action buttons (copy, thumbs up/down, retry) and a feedback endpoint are implemented. Security hardened: SQL executor enforces read-only at the SQLite engine level (`PRAGMA query_only`), tool errors return sanitized messages (no tracebacks), LLM provider switch validates before mutating settings and rolls back on failure, feedback rating constrained to `Literal["up", "down"]`. System prompt extracted into Jinja2 template. `LLMProvider` protocol includes a `model` property. VectorStore implementations verified against the protocol at import time. Conversation list query optimized (N+1 eliminated). Admin system implemented with multi-tenant feature toggles, org branding, and user-org mappings. Statistical analysis tools implemented (descriptive stats, hypothesis testing, correlation, distribution fitting). Statistician system prompt template created. Frontend admin panel with feature toggle, branding, and user mapping editors. Fourth Zustand store (client-config) manages org-level feature flags and branding. Conversation search implemented. Theme toggle (dark/light) with localStorage sync. Cloud Run deployment with min-instances=1 to eliminate cold starts.

### Implemented
- **Analyst agent** (`agents/analyst.py`) — Full tool-calling loop: RAG retrieval -> LLM -> tool execution (run_sql, get_schema, search_similar) -> streaming response
- **Tool ABC + ToolRegistry** (`agents/tool_base.py`, `agents/tools.py`) — `Tool` abstract base class with `ToolRegistry` for dispatch. 3 concrete tools (`RunSqlTool`, `GetSchemaTool`, `SearchSimilarTool`). New tools added by subclassing + `registry.register()`. Error responses sanitized (no tracebacks leaked to LLM or user)
- **LLM Factory** (`llm/factory.py`) — Registry-based `create_llm(provider, settings)` replaces duplicated if/else blocks. Lazy imports avoid pulling in provider dependencies at module level
- **LLM providers** (`llm/gemini.py`, `llm/ollama.py`) — Both Gemini and Ollama working with tool calling, streaming, and message conversion
- **Runtime LLM switching** — `/api/config/switch` endpoint uses `create_llm()` to hot-swap the LLM provider and model without restart
- **VectorStoreBackend Protocol** (`rag/base.py`) — `@runtime_checkable` protocol decouples RAG consumers from ChromaDB. `InMemoryVectorStore` (`rag/memory.py`) provides a zero-dependency test backend
- **RAG store** (`rag/store.py`) — `ChromaVectorStore` (aliased as `VectorStore`) with 4 collections (qa_pairs, ddl, docs, findings), semantic search, auto-deduplication via SHA256 IDs
- **Database layer** (`db/connector.py`, `db/schema.py`) — SQLAlchemy wrapper with row limits, timeouts, schema introspection
- **Training bootstrap** (`training/trainer.py`) — Auto-loads DDL, documentation, 12 example Q&A pairs into RAG on startup
- **Conversation memory** — Dual-store: in-memory LRU for LLM context + SQLite-backed persistent store for conversation history
- **Authentication** (`auth/`) — JWT (HS256) + bcrypt password hashing + HttpOnly cookie sessions. Default admin user auto-seeded on startup
- **API** (`api/routes.py`) — 16 endpoints: chat (SSE), chat/poll, train, schema, health, config, config/switch, sql/execute, auth (login/logout/me), conversations CRUD, feedback
- **SQL Executor** — `POST /api/sql/execute` with dual read-only enforcement (regex blocklist + SQLite `PRAGMA query_only`)
- **Data generator** (`generate_data.py`) — 250K transactions, 17 columns, 80MB SQLite DB, reproducible (seed=42)
- **Tests** — 3 test files (agent, db, rag) with pytest-asyncio fixtures
- **Config** (`config.py`) — Pydantic Settings with LLM provider toggle, DB URL, agent limits, auth settings
- **Frontend chat UI** — Next.js 16 + React 19 with SSE streaming, Zustand state, agent step timeline
- **Frontend layout** — 3-column layout: conversation history | chat | agent process steps. Responsive sidebars
- **Frontend chunk rendering** — 6 chunk types rendered in real-time: status, tool_call, sql, tool_result, answer, error
- **Frontend auth** — Login page, AuthGuard wrapper, session checking, logout
- **Frontend model selector** — Provider/model dropdown in header with runtime switching
- **Frontend SQL executor** — Right-side sheet panel with read-only SQL editor, results table, execution stats
- **Frontend chart rendering** — Auto-detects bar/pie/line charts from query results via heuristic detection
- **LLM error handling** — All LLM calls wrapped in try/except; failures yield `error` ChatChunk with descriptive message instead of crashing the stream
- **Ollama timeout + validation** — 120s timeout on AsyncClient; model existence validated via `client.show()` on provider switch (HTTP 503 on failure)
- **Conversation persistence fix** — `get_or_create_conversation` bridges frontend-generated IDs with backend SQLite store; lazy-loads messages when clicking old conversations
- **Message action buttons** — Copy prompt/response, thumbs up/down, retry (hover toolbar via `group/message` CSS); `MessageActions` component
- **Feedback endpoint** — `POST /api/feedback` persists `FeedbackRecord` (user_id, conversation_id, message_id, rating, comment)
- **UserMenu component** — Extracted from Header; avatar + dropdown with email + sign out
- **Jinja2 prompt templates** — System prompt extracted into `prompts/analyst_system.j2` with conditional RAG sections; rendered via `prompts.render()`
- **Security hardening** — Tool errors sanitized (no tracebacks), SQL executor uses engine-level `PRAGMA query_only`, LLM switch validates before mutating settings with rollback, feedback rating typed as `Literal["up", "down"]`
- **Chat route deduplication** — Shared `_prepare_chat()` helper eliminates duplicated setup logic between SSE and poll endpoints
- **Admin system** (`admin/`) — Multi-tenant configuration with feature toggles (6 switches: sql_executor, model_switching, rag_training, chart_rendering, conversation_export, agent_process_sidebar), org branding (display name, logo URL, CSS theme overrides), user-org email mappings, admin email domains. JSON config stored on disk. Admin-only CRUD endpoints + public `/api/client-config` for resolved user config
- **Statistical tools** (`agents/stat_tools.py`) — 4 tools for the statistician agent: `compute_descriptive_stats` (count, mean, std, quartiles, skewness, kurtosis), `test_hypothesis` (chi-squared, t-test, Mann-Whitney, ANOVA, z-proportion), `compute_correlation` (Pearson, Spearman, Kendall with p-values), `fit_distribution` (normal, exponential, lognormal, gamma, Weibull ranking by KS-test)
- **Statistician system prompt** (`prompts/statistician_system.j2`) — Statistical rigor rules: always state hypotheses, report p-values + effect sizes + CIs, check sample size (n<30 → non-parametric), Bonferroni correction for multiple comparisons, correlation != causation
- **Frontend admin panel** (`app/admin/`) — Admin page with guards, feature toggle switches, branding editor (display name, logo preview, theme colors), user-org mapping table, admin domain list
- **Client config store** (`stores/client-config-store.ts`) — 4th Zustand store: fetches org config, applies branding CSS variables, sets document title, provides `isFeatureEnabled()` helper
- **Conversation search** — Full-text search across conversation titles and messages via `GET /api/conversations/search?q=`
- **Theme toggle** — Dark/light mode with localStorage persistence, storage event sync across tabs, `.dark` class on `<html>`
- **Input toolbar** (`components/chat/input-toolbar.tsx`) — Send/stop button, model selector dropdown, agent mode toggle
- **Search results** (`components/sidebar/search-results.tsx`) — Highlighted matched text in conversation titles and messages
- **Cloud Run scaling** — Min-instances 1, max-instances 3 to eliminate cold starts; CPU boost enabled

### Not Yet Implemented (stubs or planned) — as of Feb 17
> **Update (Mar 2):** Most items below have since been implemented. See `docs/` for current state.

- ~~**Orchestrator** (`agents/orchestrator.py`) — 6-line stub~~ → **DONE**: Full orchestrator planner + DAG executor (`orchestrator_planner.py`, `dag_executor.py`)
- ~~**Statistician agent** — File does not exist yet~~ → **DONE**: Quant analyst agent (`quant_analyst.py`) with 6 statistical tools
- ~~**Creative Narrator agent** — File does not exist yet~~ → **DONE**: Response synthesizer (`response_generator.py`) + insight quality gate
- ~~**Anomaly Detector** — File does not exist yet~~ → Replaced by enrichment evaluator pipeline and automated insights
- **Observability** (`observability/tracer.py`, `observability/store.py`) — Still stubs, not implemented
- ~~**Ambiguity detection**~~ → **DONE**: Clarifier agent (`clarifier.py`) with `ClarifyTool`
- **Additionally implemented since Feb 17:**
  - Deep think mode (dimension extraction, investigation pipeline)
  - Automations system (scheduler, evaluator, triggers, notifications)
  - Insights system (auto-generated, bookmarking, quality gate)
  - Multi-dataset support (upload, schema inference, stats computation)
  - Vertex AI LLM provider
  - 14 advanced analytics tools
  - 13 additional Jinja2 prompt templates
  - User registration
  - 3 additional Zustand stores (insight, automation, notification)
  - Workflow builder with React Flow visual DAG editor

---

## 3. Architecture Decision: From-Scratch Engine (DONE)

Vanna was replaced with a from-scratch engine (~600 lines across analyst, tools, LLM providers, RAG store). Rationale:
1. **Custom agent loop** — multi-step tool-calling reasoning, not single-shot SQL
2. **Multi-agent orchestration** — analyst -> statistician -> narrator pipeline (analyst done, rest planned)
3. **Full explainability control** — layered responses, data provenance, confidence caveats
4. **Custom SSE streaming** — stream each step to the frontend with typed chunks
5. **Observability hooks** — instrument every step for the dashboard (planned)
6. **Ambiguity detection** — ask clarifying questions when queries are vague (planned)

**Ported from the Vanna prototype:**
- `generate_data.py` — data generator (working, 250K rows)
- Training data — DDL, documentation, 12 example queries (loaded into ChromaDB on startup)
- System prompt design — business vocabulary, caveats, provenance rules embedded in analyst prompt

---

## 4. System Architecture

> Legend: **[DONE]** = implemented, **[STUB]** = file exists but empty/minimal, **[PLANNED]** = not started

```
+------------------------------------------------------------------+
|                     Next.js Frontend [DONE]                       |
|                                                                   |
|  +---------------+  +---------------+  +------------------------+ |
|  |   Chat UI     |  |  Automations  |  |   SQL Executor         | |
|  |   (SSE)       |  |  + Insights   |  |   [DONE]               | |
|  |   [DONE]      |  |  [DONE]       |  |   (Sheet panel)        | |
|  +------+--------+  +-------+-------+  +----------+-------------+ |
|         |                    |                     |               |
|  +------+--------+  +-------+-------+  +----------+-------------+ |
|  |   Auth Flow   |  |  Model Select |  |   Admin Panel          | |
|  |   [DONE]      |  |  [DONE]       |  |   [DONE]               | |
|  +------+--------+  +-------+-------+  +----------+-------------+ |
+------------------------------------------------------------------+
          |                    |                     |
          v                    v                     v
+------------------------------------------------------------------+
|                     FastAPI Backend [DONE]                         |
|                                                                   |
|  POST /api/chat (SSE) [DONE]    GET /api/config     [DONE]       |
|  POST /api/chat/poll  [DONE]    POST /api/config/switch [DONE]   |
|  POST /api/train      [DONE]    POST /api/sql/execute [DONE]     |
|  GET  /api/schema     [DONE]    /api/automations/*  [DONE]       |
|  GET  /api/health     [DONE]                                     |
|  POST /api/auth/login [DONE]    GET /api/conversations [DONE]    |
|  POST /api/auth/logout[DONE]    CRUD /api/conversations/ [DONE]  |
|  GET  /api/auth/me    [DONE]                                     |
|                                                                   |
|  +-------------------------------------------------------------+ |
|  |                    Orchestrator [DONE]                        | |
|  |                                                              | |
|  |  +-----------+  +---------------+  +----------------------+  | |
|  |  | Analyst   |->| Quant Analyst |->| Response Synthesizer |  | |
|  |  | [DONE]    |  | [DONE]        |  | [DONE]               |  | |
|  |  +-----------+  +---------------+  +----------------------+  | |
|  |                                                              | |
|  |  +--------------------------------------------------------+  | |
|  |  | Deep Think (investigation pipeline) [DONE]              |  | |
|  |  +--------------------------------------------------------+  | |
|  +-------------------------------------------------------------+ |
|                                                                   |
|  +-----------+  +-----------+  +-----------+  +----------------+ |
|  | LLM (3)   |  | RAG       |  | SQLite    |  | Observability  | |
|  | [DONE]    |  | [DONE]    |  | [DONE]    |  | [STUB]         | |
|  +-----------+  +-----------+  +-----------+  +----------------+ |
|                                                                   |
|  +-----------+  +-----------+                                    |
|  | Auth/JWT  |  | Persist.  |                                    |
|  | [DONE]    |  | ConvStore |                                    |
|  |           |  | [DONE]    |                                    |
|  +-----------+  +-----------+                                    |
+------------------------------------------------------------------+
```

### Current Data Flow (single-agent, what actually runs today)

```
User Query -> POST /api/chat
  -> Authenticate (JWT cookie -> get_current_user)
  -> analyst_loop()
    -> RAG retrieval (qa_pairs, ddl, docs, findings from ChromaDB)
    -> Build system prompt (DDL + docs + domain rules + RAG context)
    -> LLM chat (Gemini or Ollama) with tool definitions
    -> Tool-calling loop (max 10 iterations):
        -> run_sql    -> DatabaseConnector -> SQLite
        -> get_schema -> Schema introspection -> DDL
        -> search_similar -> VectorStore -> ChromaDB
    -> Final LLM response (answer text)
    -> Auto-save learned QA pair to RAG
  -> Stream ChatChunks via SSE (status, sql, tool_call, tool_result, answer, error)
  -> Save user message + assistant answer to:
     - In-memory ConversationStore (for LLM context)
     - PersistentConversationStore (for history replay)
```

---

## 5. Agent Architecture (Detail)

### 5.1 Analyst Agent — The Core Loop

**File:** `agents/analyst.py`

The analyst is the primary agent. It receives a natural language question and produces a data-backed answer through iterative tool calling.

**Execution flow:**

```
1. RAG Retrieval
   +-- search_qa(question, n=5)       -> similar past Q->SQL pairs
   +-- search_ddl(question, n=3)      -> relevant table schemas
   +-- search_docs(question, n=3)     -> business documentation
   +-- search_findings(question, n=2) -> anomaly findings

2. Build System Prompt
   +-- Identity & purpose
   +-- Database schema (DDL constant)
   +-- Business context (DOCUMENTATION constant)
   +-- Tool definitions (run_sql, get_schema, search_similar)
   +-- Domain rules (7 rules: SELECT only, NULL semantics, fraud_flag,
   |   ROUND(), correlation != causation, small samples, execute before answering)
   +-- Response structure (5-layer: answer -> evidence -> provenance -> caveats -> follow-ups)
   +-- RAG context (injected similar queries, introspected schema, docs, findings)

3. Inject conversation history (for multi-turn context)

4. LLM Tool-Calling Loop (max 10 iterations)
   +-- Send messages + tool definitions to LLM (wrapped in try/except)
   +-- If LLM call fails (network, timeout, model not found):
   |   +-- Log error with traceback
   |   +-- Yield ChatChunk(type="error", content="LLM request failed: {exc}")
   |   +-- Return (exit generator cleanly)
   +-- If LLM returns tool_calls:
   |   +-- Yield ChatChunk(type="tool_call") for each call
   |   +-- If run_sql: yield ChatChunk(type="sql") with the SQL
   |   +-- Execute tool -> get result
   |   +-- Yield ChatChunk(type="tool_result") with result
   |   +-- Append tool result to messages, continue loop
   +-- If LLM returns text (no tool_calls):
       +-- Yield ChatChunk(type="answer") with final response
       +-- Extract SQL from conversation, auto-save Q->SQL pair to RAG
       +-- Break loop

5. If max iterations exhausted -> yield ChatChunk(type="error")
```

**System prompt structure** (Jinja2 template: `prompts/analyst_system.j2`):
- Identity as InsightXpert AI data analyst
- Full DDL for the transactions table (17 columns)
- Business documentation (column descriptions, domain rules)
- 7 domain rules (SELECT only, NULL handling, fraud_flag semantics, ROUND(2), correlation != causation, small sample flags, execute before answering)
- 5-layer response structure requirement
- RAG context dynamically injected per query via conditional Jinja2 blocks (`{% if similar_qa %}`, etc.)

### 5.2 Tool Framework

**Files:** `agents/tool_base.py` (ABC + registry), `agents/tools.py` (concrete tools)

The tool framework uses an abstract base class and registry pattern:

```python
# agents/tool_base.py
class ToolContext:        # Holds db, rag (typed as VectorStoreBackend via TYPE_CHECKING), row_limit
class Tool(ABC):          # Abstract: name, description, get_args_schema(), execute(), get_definition()
class ToolRegistry:       # register(tool), get_schemas(), execute(name, args, context) — sanitized errors
```

Three concrete tools (each a `Tool` subclass in `agents/tools.py`):

| Tool Class | LLM Name | Purpose | Arguments | Returns |
|-----------|----------|---------|-----------|---------|
| `RunSqlTool` | `run_sql` | Execute SELECT query on SQLite | `sql: string` | `{rows: [...], row_count: N}` |
| `GetSchemaTool` | `get_schema` | Get CREATE TABLE DDL | `tables?: string[]` | DDL string or table info JSON |
| `SearchSimilarTool` | `search_similar` | Search ChromaDB knowledge base | `query: string, collection: "qa_pairs"\|"ddl"\|"docs"` | Array of `{document, metadata, distance}` |

The `default_registry()` function creates a pre-loaded `ToolRegistry`. The analyst loop accepts an optional `tool_registry` parameter, defaulting to `default_registry()` if not provided. Adding a new tool requires subclassing `Tool` and calling `registry.register()`.

Backward-compatible `TOOL_DEFINITIONS` list and `execute_tool()` function are still exported for existing callers.

### 5.3 LLM Provider Abstraction

**Files:** `llm/base.py` (protocol), `llm/factory.py` (factory), `llm/gemini.py`, `llm/ollama.py`

```python
# llm/base.py — Protocol
class LLMProvider(Protocol):
    model: str                                            # Public read-only property
    async def chat(messages, tools) -> LLMResponse       # Non-streaming
    async def chat_stream(messages, tools) -> AsyncGenerator[LLMChunk]  # Streaming

# llm/factory.py — Registry-based factory
_REGISTRY: dict[str, Callable[[Settings], LLMProvider]]  # "gemini" -> _create_gemini, etc.
def create_llm(provider: str, settings: Settings) -> LLMProvider  # Raises ValueError on miss

@dataclass
class LLMResponse:
    content: str | None          # Text response
    tool_calls: list[ToolCall]   # Tool invocations

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
```

**Factory pattern** — `create_llm("gemini", settings)` looks up a registry of factory functions. Each factory uses lazy imports to avoid pulling in provider dependencies at module level. Adding a new provider requires only writing the provider class and registering a factory function. Both `main.py` and `api/routes.py` use `create_llm()` instead of inline if/else blocks.

**Gemini provider** — Uses `google-genai` async client. Converts internal message format to Gemini's `Content`/`Part` types. Maps tool definitions to `FunctionDeclaration`. Handles function_call responses and multipart content.

**Ollama provider** — Uses `ollama` async client with 120s timeout. Same protocol, different wire format. Fallback for local development without API keys.

**Runtime switching** — Provider can be changed at runtime via `POST /api/config/switch`. For Ollama, the endpoint validates the model exists via `client.show(model)` before mutating any settings — returns HTTP 503 with a clear error if Ollama is unreachable or the model isn't pulled. Settings are saved before mutation and rolled back if `create_llm()` fails. On success, `app.state.llm` is replaced. No restart needed. Unknown providers return HTTP 400. Available models are served from `GET /api/config` (Gemini models are hardcoded, Ollama models are dynamically queried from the local server).

### 5.4 Multi-Agent Pipeline (Implemented)

**Files:** `agents/orchestrator_planner.py`, `agents/dag_executor.py`, `agents/response_generator.py`

> **Update (Mar 2):** This pipeline is fully implemented. The orchestrator plans a DAG of tasks, the DAG executor runs them in parallel, and the response synthesizer combines results. See `docs/agent-pipeline.md` for the current architecture.

The orchestrator routes questions through a pipeline of specialized agents:

```
User Question
      |
      v
+------------------+
|   Orchestrator    |  <- Route question, manage pipeline
+--------+---------+
         |
         +-- Ambiguity check: Is the question too vague? -> Ask clarifying question
         |
         v
+------------------+
|  RAG Retrieval   |  <- Similar QA pairs, DDL, docs, anomaly findings
+--------+---------+
         |
         v
+------------------+
|    Analyst        |  <- NL->SQL, tool-calling loop, raw data results
|  (LLM + tools)   |
+--------+---------+
         | result_data
         v
+------------------+
|  Statistician     |  <- Pure Python: rate comparisons, benchmarks,
|  (no LLM call)   |     sample size checks, outlier detection
+--------+---------+
         | enriched_data
         v
+------------------+
|  Creative         |  <- LLM call: leadership-friendly narrative
|  Narrator         |     with layered structure, provenance, caveats
+--------+---------+
         |
         v
  Save Q->SQL pair to RAG
```

**Agent Roles:**

| Agent | Purpose | LLM? | Tools |
|-------|---------|------|-------|
| **Analyst** [DONE] | NL->SQL, execute queries, return raw results | Yes (Gemini) | `run_sql`, `get_schema`, `search_similar` + 14 advanced tools |
| **Quant Analyst** [DONE] | Statistical analysis with Python tools | Yes (Gemini) | `run_sql`, `descriptive_stats`, `hypothesis_test`, `correlation`, `fit_distribution`, `run_python` |
| **Response Synthesizer** [DONE] | Combine multi-task results into coherent response | Yes (Gemini) | None (pure LLM generation) |
| **Deep Think** [DONE] | 5W1H dimension extraction → investigation → synthesis | Yes (Gemini) | Full analyst tool set |

---

## 6. Authentication & Authorization

### 6.1 Auth Architecture

**Files:** `auth/routes.py`, `auth/security.py`, `auth/dependencies.py`, `auth/models.py`, `auth/seed.py`

```
Login Flow:
  POST /api/auth/login {email, password}
    -> bcrypt.verify(password, hashed_password)
    -> create_access_token(user_id, email) [HS256 JWT]
    -> Set HttpOnly cookie "access_token"
    -> Return {id, email}

Protected Route Flow:
  Request with cookie
    -> get_current_user() dependency
    -> Extract token from cookie
    -> decode_access_token(token, secret_key)
    -> Fetch User from SQLite auth DB
    -> Inject user into route handler
```

**ORM Models (SQLAlchemy):**
- `User`: id (UUID), email (unique), hashed_password, is_active, created_at
- `ConversationRecord`: id, user_id (FK), title, created_at, updated_at
- `MessageRecord`: id, conversation_id (FK), role, content, chunks_json, created_at
- `FeedbackRecord`: id, user_id (FK), conversation_id, message_id, rating ("up"/"down"), comment, created_at

**Default Credentials:** `admin@insightxpert.ai` / `admin123` (auto-seeded on startup via `auth/seed.py`)

### 6.2 Frontend Auth Flow

**Files:** `stores/auth-store.ts`, `components/auth/auth-guard.tsx`, `app/login/page.tsx`

1. **App load** -> `checkAuth()` -> `GET /api/auth/me` -> set user or null
2. **AuthGuard** wraps protected pages -> redirects to `/login` if no user
3. **Login page** -> form submit -> `POST /api/auth/login` -> set user -> redirect to `/`
4. **Logout** -> header button -> `POST /api/auth/logout` -> clear user -> redirect to `/login`

---

## 7. Frontend Architecture

### 7.1 Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 16.1.6 | React framework (App Router) |
| React | 19.2.3 | UI library |
| TypeScript | 5.x | Type safety |
| Zustand | 5.0.11 | State management (4 stores) |
| Tailwind CSS | 4 | Utility-first styling |
| shadcn/ui | New York | Component library (Radix primitives) |
| Framer Motion | 12.34.0 | Layout animations |
| Recharts | 2.15.4 | Data visualization |
| React Markdown | 10.1.0 | Answer rendering |
| React Syntax Highlighter | 16.1.0 | SQL code display |

### 7.2 Layout

**File:** `components/layout/app-shell.tsx`

Three-column responsive layout:

```
+------------------------------------------------------------------+
|                         Header                                    |
|  [InsightXpert]           [Provider / Model]  [SQL] [user] [out] |
+-------------+----------------------------------+-----------------+
|             |                                  |                 |
|  Left       |         Chat Panel               |    Right        |
|  Sidebar    |                                  |    Sidebar      |
|             |  +----------------------------+  |                 |
|  Conver-    |  |     Message List           |  |  Agent          |
|  sation     |  |                            |  |  Process        |
|  History    |  |  [User bubble]             |  |  Steps          |
|             |  |  [Assistant bubble]        |  |                 |
|  - Chat 1   |  |    +- Status chunk         |  |  o Searching    |
|  - Chat 2   |  |    +- SQL chunk            |  |  * Running SQL  |
|  - Chat 3   |  |    +- Result table + chart |  |  v 10 rows      |
|             |  |    +- Answer (markdown)     |  |  v Answer       |
|             |  |                            |  |                 |
|             |  +----------------------------+  |                 |
|             |  +----------------------------+  |                 |
|             |  |     Message Input           |  |                 |
|             |  +----------------------------+  |                 |
+-------------+----------------------------------+-----------------+
```

- **Header:** Logo + Model selector (Provider / Model dropdowns with chevrons) + SQL Executor button + UserMenu (avatar + dropdown with email + sign out)
- **Left sidebar:** Conversation history list with create/delete/rename. Collapsible on desktop, Sheet on mobile
- **Right sidebar:** Real-time agent process steps timeline. Shows each step's status (pending/running/done/error)
- **Chat panel:** Message list with auto-scroll, chunk-by-chunk rendering, message input with suggested questions on welcome

### 7.3 State Management (7 Zustand Stores)

> **Update (Mar 2):** Now 7 stores. The 4 below are the originals. 3 additional stores were added: `insight-store.ts`, `automation-store.ts`, `notification-store.ts`. See `WALKTHROUGH.md` section 5.3 for the full list.

**`stores/auth-store.ts`**
```
State: user | null, isLoading, error
Actions: login(email, password), logout(), checkAuth()
```

**`stores/chat-store.ts`**
```
State: conversations[], activeConversationId, isStreaming, agentSteps[], sidebarOpen flags
Actions: newConversation(), addUserMessage(), appendChunk(), finishStreaming(),
         deleteConversation(), renameConversation(), addAgentStep(), updateAgentStep(),
         loadConversationMessages(id), setActiveConversation(id) [with lazy-load]
Persistence: Fetches from /api/conversations on init, CRUD via REST API,
             lazy-loads messages via GET /api/conversations/{id} on click
```

**`stores/settings-store.ts`**
```
State: currentProvider, currentModel, providers[], loading, agentMode
Actions: fetchConfig() [GET /api/config], switchModel(provider, model) [POST /api/config/switch],
         setAgentMode()
         Optimistic updates with rollback on failure
```

**`stores/client-config-store.ts`**
```
State: config (OrgConfig | null), isAdmin, orgId, isLoading
Actions: fetchConfig() [GET /api/client-config]
         Applies branding CSS variables on fetch, sets document title
         Provides isFeatureEnabled() helper for conditional UI rendering
```

### 7.4 SSE Streaming

**Files:** `hooks/use-sse-chat.ts`, `lib/sse-client.ts`

The `useSSEChat()` hook manages the full streaming lifecycle:

1. Creates/reuses a conversation
2. Adds user message to store
3. Opens SSE connection to `POST /api/chat` (with credentials for auth)
4. Parses each incoming chunk (`parseChunk()` from `lib/chunk-parser.ts`)
5. Appends chunk to assistant message
6. Creates/updates AgentStep entries for the right sidebar timeline
7. Tracks "last running step" to mark it done when the next chunk arrives
8. Handles errors and stream completion

### 7.5 Chunk Rendering Pipeline

**Files:** `components/chunks/`

Each SSE chunk type maps to a dedicated React component:

| Chunk Type | Component | Renders |
|------------|-----------|---------|
| `status` | `StatusChunk` | Animated spinner with label |
| `tool_call` | `ToolCallChunk` | Animated ping indicator with tool name |
| `sql` | `SqlChunk` | Collapsible syntax-highlighted SQL (react-syntax-highlighter, vs2015) with copy button |
| `tool_result` | `ToolResultChunk` | Collapsible data table + auto-detected chart (bar/pie/line via `chart-detector.ts`) |
| `answer` | `AnswerChunk` | Markdown via react-markdown + remark-gfm with custom component styling |
| `error` | `ErrorChunk` | Destructive-styled error card |

The `ChunkRenderer` component routes each chunk to the correct renderer. Charts are auto-detected by `lib/chart-detector.ts` using heuristics (column types, row count, temporal detection).

### 7.6 SQL Executor Panel

**File:** `components/sql/sql-executor.tsx`

Opens as a right-side Sheet panel (640px) from a header button:
- Textarea editor with monospace font, placeholder SQL
- **Cmd/Ctrl+Enter** keyboard shortcut or Execute button
- Results: stats bar (row count + execution time) + scrollable table with sticky headers
- Error display for blocked write queries or SQL syntax errors
- "Read-only" badge in header — write operations blocked server-side

### 7.7 Model Selector

**File:** `components/layout/model-selector.tsx`

Breadcrumb-style selector in the header: `[Provider v] / [Model v]`

- Left dropdown: Provider (Gemini, Ollama) with `ChevronsUpDown` icon
- Right dropdown: Model (filtered by selected provider) with `ChevronsUpDown` icon
- Uses Radix `DropdownMenuRadioGroup` for single-selection
- Fetches config on mount, applies optimistic updates with rollback

### 7.8 Routing & Auth Guard

| Route | Component | Auth Required |
|-------|-----------|---------------|
| `/` | `AppShell` > `ChatPanel` | Yes (AuthGuard) |
| `/login` | Login form | No |
| `/register` | Registration form | No |
| `/admin` | Admin dashboard | Yes (AdminGuard) |
| `/admin/automations` | Automation management | Yes (AdminGuard) |
| `/admin/notifications` | Notification management | Yes (AdminGuard) |

`AuthGuard` calls `checkAuth()` on mount, shows loading spinner while verifying, redirects to `/login` if session is invalid.

### 7.9 Styling

- **Method:** Tailwind CSS 4 with CSS custom properties (OKLch color space)
- **Theme:** Dark mode by default (`html className="dark"`)
- **Glass effect:** Custom `.glass` utility class (backdrop-blur-12px, semi-transparent)
- **Fonts:** Inter (body), JetBrains Mono (code/data)
- **Components:** shadcn/ui New York style with Radix UI primitives
- **Animations:** Framer Motion for sidebar collapse/expand, CSS for chunk entrance

---

## 8. Data Layer

### 8.1 Database Connector

**File:** `db/connector.py`

SQLAlchemy engine wrapper with safety features:
- `connect(url)` — Initialize engine with connection pooling + pre-ping
- `execute(sql, row_limit=1000, timeout=30, read_only=False)` — Execute SQL, return JSON-serializable rows, enforce row limit. When `read_only=True`, sets `PRAGMA query_only = ON` on the connection before executing — enforces read-only at the SQLite engine level regardless of SQL content
- `get_tables()` — Introspect table names
- `disconnect()` — Dispose engine

### 8.2 Schema Introspection

**File:** `db/schema.py`

- `get_table_info(engine, table_name)` -> dict with columns, types, keys, foreign keys
- `get_schema_ddl(engine)` -> Full CREATE TABLE DDL for all tables

### 8.3 SQL Executor Endpoint

**File:** `api/routes.py` — `POST /api/sql/execute`

Dual-layer read-only enforcement:

1. **Regex blocklist** (fast reject) — Compiled regex catches common write operations before query execution:
```python
_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|
         GRANT|REVOKE|ATTACH|DETACH|PRAGMA\s+\w+\s*=)\b",
    re.IGNORECASE,
)
```

2. **Engine-level enforcement** — Calls `db.execute(sql, read_only=True)` which sets `PRAGMA query_only = ON` on the SQLite connection. This blocks writes at the database engine level regardless of SQL syntax tricks (comments, unicode, multi-statement).

Returns 403 with a descriptive error if the regex catches a write operation. Otherwise executes the query with the configured `sql_row_limit` and `sql_timeout_seconds`, returning `{columns, rows, row_count, execution_time_ms}`.

### 8.4 Data Generator

**File:** `generate_data.py`

Generates 250,000 synthetic Indian digital payment transactions with:
- Realistic distributions for 17 columns
- Deterministic seed (42) for reproducibility
- 8 database indices for query performance
- Output: `insightxpert.db` (~80MB SQLite file)

### 8.5 Training Data

**Files:** `training/schema.py`, `training/documentation.py`, `training/queries.py`

| File | Content |
|------|---------|
| `schema.py` | DDL constant for `transactions` table (17 columns) |
| `documentation.py` | Business context: column descriptions, NULL semantics, domain rules |
| `queries.py` | 12 example Q->SQL pairs across 6 categories (descriptive, comparative, temporal, segmentation, correlation, risk) |

The `Trainer` class (`training/trainer.py`) loads all training data into ChromaDB on startup.

---

## 9. RAG & Memory Systems

### 9.1 Vector Store

**Files:** `rag/base.py` (protocol), `rag/store.py` (ChromaDB), `rag/memory.py` (in-memory for testing)

The vector store uses a `VectorStoreBackend` protocol (`@runtime_checkable`) defining all 8 methods (`add_qa_pair`, `add_ddl`, `add_documentation`, `add_finding`, `search_qa`, `search_ddl`, `search_docs`, `search_findings`). All consumers (e.g., `Trainer`, `ToolContext`) type-hint against the protocol, not the concrete implementation. Both `ChromaVectorStore` and `InMemoryVectorStore` are verified against the protocol at import time via `issubclass` assertions in `rag/__init__.py`.

**`ChromaVectorStore`** (`rag/store.py`, aliased as `VectorStore` for backward compat) — ChromaDB embedded persistent client with 4 collections:

| Collection | Content | Search Method | Default N |
|-----------|---------|---------------|-----------|
| `qa_pairs` | Question->SQL pairs (hand-crafted + auto-learned) | `search_qa()` | 5 |
| `ddl` | Table DDL and schema | `search_ddl()` | 3 |
| `docs` | Business documentation and guidelines | `search_docs()` | 3 |
| `findings` | Anomaly findings from background analysis | `search_findings()` | 3 |

**Auto-deduplication:** Document IDs are SHA256 hashes of content (first 16 chars). Upserts prevent duplicates.

**Auto-learning:** When the analyst successfully generates SQL, the question->SQL pair is automatically saved to the `qa_pairs` collection, improving future retrieval.

**`InMemoryVectorStore`** (`rag/memory.py`) — Dict-based storage with `difflib.SequenceMatcher` for similarity ranking. Satisfies `VectorStoreBackend` structurally. Zero external dependencies — designed for unit tests and development without ChromaDB.

### 9.2 Conversation Memory (Dual-Store)

**In-Memory Store** (`memory/conversation_store.py`):
- Purpose: Fast LLM context retrieval
- **LRU eviction** — max 500 conversations, oldest evicted first
- **TTL expiry** — conversations expire after 2 hours of inactivity
- **History depth** — last 20 turns per conversation injected into LLM context
- **Condensed storage** — only user messages + assistant final answers (no tool intermediaries)

**Persistent Store** (`auth/conversation_store.py`):
- Purpose: Long-term conversation history with full message replay
- Storage: SQLite (`insightxpert_auth.db`) via SQLAlchemy ORM
- Tables: `conversations`, `messages`, `feedback`
- Features: Full CRUD, message chunks JSON storage, user_id isolation
- Conversation listing uses a single subquery join to fetch last messages (no N+1 queries)
- `get_or_create_conversation(id, user_id, title)` — Bridges frontend-generated IDs with backend storage. Looks up by ID; if not found, creates with that exact ID. Solves the mismatch where frontend generates client-side IDs that the backend never persisted.
- Frontend loads conversation list on init via `GET /api/conversations`; lazy-loads messages via `GET /api/conversations/{id}` when clicking old conversations

**Data Flow:**
```
User Message
+-> In-memory store (for LLM context in next turn)
+-> Persistent store (for conversation list and history replay)

Assistant Answer
+-> In-memory store (for next turn context)
+-> Persistent store + chunks JSON (for full replay in UI)
```

---

## 10. API Endpoints

### Implemented

| Method | Path | Auth | Request | Response | Purpose |
|--------|------|------|---------|----------|---------|
| POST | `/api/auth/login` | No | `{email, password}` | `{id, email}` + Cookie | Authenticate |
| POST | `/api/auth/logout` | No | — | `{status: ok}` | Clear auth cookie |
| GET | `/api/auth/me` | Yes | — | `{id, email}` | Get current user |
| POST | `/api/chat` | Yes | `{message, conversation_id?}` | SSE stream of `ChatChunk` | Streaming text-to-SQL |
| POST | `/api/chat/poll` | Yes | `{message, conversation_id?}` | `{chunks: ChatChunk[]}` | Blocking text-to-SQL |
| POST | `/api/train` | Yes | `{type, content, metadata?}` | `{status, id}` | Train RAG (qa_pair, ddl, documentation) |
| GET | `/api/schema` | Yes | — | `{ddl, tables}` | Introspect DB schema |
| GET | `/api/config` | Yes | — | `{current_provider, current_model, providers[]}` | List LLM providers & models |
| POST | `/api/config/switch` | Yes | `{provider, model}` | `{provider, model}` | Switch LLM at runtime |
| POST | `/api/sql/execute` | No | `{sql}` | `{columns, rows, row_count, execution_time_ms}` | Execute read-only SQL |
| GET | `/api/conversations` | Yes | — | `ConversationSummary[]` | List conversations |
| GET | `/api/conversations/{id}` | Yes | — | `ConversationDetail` | Get conversation + messages |
| DELETE | `/api/conversations/{id}` | Yes | — | `{status: ok}` | Delete conversation |
| PATCH | `/api/conversations/{id}` | Yes | `{title}` | `{status: ok}` | Rename conversation |
| POST | `/api/feedback` | Yes | `{conversation_id, message_id, rating, comment?}` | `{status: ok}` | Submit feedback |
| GET | `/api/health` | No | — | `{status: "ok", timestamp}` | Health check |
| GET | `/api/client-config` | Yes | — | `ResolvedClientConfig` | Get resolved org config (features, branding) |
| GET | `/api/admin/config` | Admin | — | `ClientConfig` | Get full admin config |
| PUT | `/api/admin/config` | Admin | `{admin_domains?, user_org_mappings?, defaults?}` | `ClientConfig` | Update global config |
| GET | `/api/admin/organizations` | Admin | — | `{organizations: [...]}` | List organizations |
| GET | `/api/admin/config/{org_id}` | Admin | — | `OrgConfig` | Get org config |
| PUT | `/api/admin/config/{org_id}` | Admin | `OrgConfig` | `OrgConfig` | Upsert org config |
| DELETE | `/api/admin/config/{org_id}` | Admin | — | `{status: ok}` | Delete org config |
| GET | `/api/conversations/search` | Yes | `?q=term` | `ConversationSummary[]` | Full-text search conversations |

**ChatChunk types:** `status`, `sql`, `tool_call`, `tool_result`, `answer`, `error`, `clarification`, `stats_context`, `insight`, `enrichment_trace`, `orchestrator_plan`, `agent_trace`, `metrics`

### Additional Endpoints (implemented since Feb 17)

> See `docs/api-reference.md` for the full 50+ endpoint reference.

| Category | Endpoints |
|----------|-----------|
| **Automations** | CRUD, toggle, run, run history, generate SQL (8 endpoints) |
| **Insights** | List, all, count, bookmark, delete (5 endpoints) |
| **Notifications** | List, all, count, mark read, mark all read (5 endpoints) |
| **Datasets** | List, upload, get, delete, schema, sample (6 endpoints) |
| **Trigger Templates** | List, create, delete (3 endpoints) |
| **Auth** | Register endpoint added |

---

## 11. End-to-End Data Flow

```
+-- User types: "What is the average txn amount by merchant category?" --+
+-----------------------------+------------------------------------------+
                              |
    Frontend: useSSEChat()    |
    +-- addUserMessage() -> Zustand store
    +-- startAssistantMessage()
    +-- clearAgentSteps()
    +-- Open SSE: POST /api/chat {message, conversation_id}
                              |
                              v
    Backend: routes.py        |
    +-- Authenticate (JWT cookie -> get_current_user)
    +-- Load conversation history from both stores
    +-- Save user message to both stores
    +-- Start SSE event generator from analyst_loop()
                              |
                              v
    analyst_loop()            |
    |                         |
    |  1. RAG Retrieval       |
    |  +-- search_qa -> 5 similar Q->SQL pairs
    |  +-- search_ddl -> 3 relevant schemas
    |  +-- search_docs -> 3 doc chunks
    |  +-- search_findings -> 2 anomaly findings
    |  yield: ChatChunk(type="status", "Searching knowledge base...")
    |                         | --SSE--> Frontend: appendChunk + addAgentStep(running)
    |                         |
    |  2. Build system prompt with DDL + docs + RAG context
    |  3. Inject conversation history
    |                         |
    |  4. LLM Tool-Calling Loop
    |  +-- Iteration 1 -------------------------------------------+
    |  | LLM analyzes question, decides to call run_sql            |
    |  | yield: ChatChunk(type="tool_call", tool_name="run_sql")   |
    |  |                  | --SSE--> Frontend: addAgentStep(running)|
    |  | yield: ChatChunk(type="sql", sql="SELECT ...")            |
    |  |                  | --SSE--> Frontend: SqlChunk renders SQL |
    |  |                  |                                        |
    |  | Execute: db.execute(sql, row_limit=1000)                  |
    |  | yield: ChatChunk(type="tool_result", data={rows, count})  |
    |  |                  | --SSE--> Frontend: table + chart render |
    |  +-----------------------------------------------------------+
    |  +-- Iteration 2 -------------------------------------------+
    |  | LLM sees results, generates answer                        |
    |  | yield: ChatChunk(type="answer", content="Based on...")    |
    |  |                  | --SSE--> Frontend: AnswerChunk markdown |
    |  +-----------------------------------------------------------+
    |                         |
    |  5. Auto-save Q->SQL pair to RAG (for future few-shot)
    |  yield: {"data": "[DONE]"}
    |                         | --SSE--> Frontend: finishStreaming()
    |                         |
    |  6. Save assistant answer to both conversation stores
    +--------------------------
```

---

## 12. Explainability Architecture

Maps directly to the PRD evaluation criteria (20% weight) and the QuestionBank explainability strategy.

### Response Structure (every answer)

```
+--------------------------------------------------+
|  1. DIRECT ANSWER (1-2 sentences)                |  "Bill payments have the
|     Plain language, business vocabulary            |   highest failure rate at 8.2%."
+--------------------------------------------------+
|  2. SUPPORTING EVIDENCE                           |  Breakdown table, ranked list,
|     Statistics, comparisons, benchmarks            |  "This is 2x the platform avg."
+--------------------------------------------------+
|  3. DATA PROVENANCE                               |  "Based on 62,400 bill payment
|     Scope, row count, time range                   |  transactions from Jul-Dec 2024."
+--------------------------------------------------+
|  4. CAVEATS (when applicable)                     |  "Note: Small sample for Web
|     Small samples, correlation != causation        |  users (320 records)."
+--------------------------------------------------+
|  5. FOLLOW-UP SUGGESTIONS                         |  "Want to drill down by bank?"
|     Contextual next questions                      |  "Should I compare weekday vs
|                                                    |  weekend patterns?"
+--------------------------------------------------+
```

**Current state:** The analyst agent's system prompt enforces this layered structure. Once the narrator agent is implemented, this structure will be enforced as a dedicated post-processing step.

---

## 13. Observability & Dashboard (NOT IMPLEMENTED)

### 13.1 Storage: SQLite (separate file)

```sql
-- obs.db

CREATE TABLE traces (
    id          TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT DEFAULT 'running',   -- running, completed, error
    total_ms    INTEGER
);

CREATE TABLE spans (
    id          TEXT PRIMARY KEY,
    trace_id    TEXT NOT NULL REFERENCES traces(id),
    parent_id   TEXT,
    agent       TEXT NOT NULL,             -- analyst, statistician, creative
    name        TEXT NOT NULL,             -- rag_retrieval, llm_call, sql_execution
    start_ts    TEXT NOT NULL,
    end_ts      TEXT,
    duration_ms INTEGER,
    attributes  TEXT DEFAULT '{}'          -- JSON
);

CREATE TABLE llm_calls (
    id          TEXT PRIMARY KEY,
    trace_id    TEXT NOT NULL,
    agent       TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    latency_ms  INTEGER,
    timestamp   TEXT NOT NULL
);

CREATE TABLE sql_executions (
    id          TEXT PRIMARY KEY,
    trace_id    TEXT NOT NULL,
    sql_text    TEXT NOT NULL,
    row_count   INTEGER,
    latency_ms  INTEGER,
    status      TEXT,                      -- success, error
    error_msg   TEXT,
    timestamp   TEXT NOT NULL
);
```

### 13.2 Dashboard Pages (Next.js)

| Page | What It Shows | Why It Matters for Demo |
|------|---------------|------------------------|
| **Live Trace** | Real-time view of current question flowing through agents | Shows the judges the multi-agent pipeline in action |
| **Query History** | All questions asked, SQL generated, results, timing | Demonstrates accuracy and coverage |
| **Agent Performance** | Latency breakdown per agent step, LLM token usage | Shows technical depth (Innovation, 10%) |
| **SQL Audit** | Every SQL query executed, row counts, timing | Transparency for explainability scoring |

---

## 14. Configuration

### Backend (`config.py`)

```python
class Settings(BaseSettings):
    # LLM Provider (gemini or ollama)
    llm_provider: LLMProvider = LLMProvider.GEMINI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434"

    # Database
    database_url: str = "sqlite:///./insightxpert.db"

    # Vector Store
    chroma_persist_dir: str = "./chroma_data"

    # Agent Limits
    max_agent_iterations: int = 10
    sql_row_limit: int = 1000
    sql_timeout_seconds: int = 30

    # Auth
    secret_key: str = "..."
    access_token_expire_minutes: int = 1440  # 24 hours

    # Logging
    log_level: str = "DEBUG"

    # Observability (Day 2+)
    obs_database_path: str = "./obs.db"
```

### Frontend (`lib/constants.ts`)

```typescript
API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
```

---

## 15. Project Structure

> Files marked with [DONE] exist and are implemented, [STUB] are stubs/empty, [PLANNED] are planned but don't exist yet.

```
InsightXpert/
+-- ARCHITECTURE.md                       # This file
+-- CLAUDE.md                             # AI assistant instructions
+-- README.md
+-- .env.example
+-- .gitignore
+-- prd/                                  # Problem statement & question bank
+-- postman/                              # API collection
|
+-- backend/
|   +-- pyproject.toml                    # [DONE] hatchling build, Python >=3.11
|   +-- uv.lock                           # [DONE] Pinned dependency graph
|   +-- .env.example                      # [DONE] Environment variable template
|   +-- generate_data.py                  # [DONE] 250K transaction generator (seed=42)
|   +-- insightxpert.db                   # [DONE] SQLite DB (80MB, 250K rows, 8 indices)
|   +-- insightxpert_auth.db              # [DONE] SQLite DB for auth + conversations
|   +-- chroma_data/                      # [DONE] ChromaDB persistent vector store
|   |
|   +-- src/insightxpert/
|   |   +-- __init__.py
|   |   +-- main.py                       # [DONE] FastAPI app + async lifespan
|   |   +-- config.py                     # [DONE] Pydantic Settings (LLM, DB, auth)
|   |   |
|   |   +-- api/
|   |   |   +-- routes.py                 # [DONE] 16 endpoints (chat, auth, config, sql, conv CRUD, feedback)
|   |   |   +-- models.py                 # [DONE] Pydantic models for all endpoints (incl. FeedbackRequest)
|   |   |   +-- obs_routes.py             # [PLANNED] /obs/traces, /obs/spans, /obs/stats
|   |   |
|   |   +-- auth/
|   |   |   +-- routes.py                 # [DONE] Login, logout, me endpoints
|   |   |   +-- models.py                 # [DONE] User, ConversationRecord, MessageRecord, FeedbackRecord ORM
|   |   |   +-- security.py               # [DONE] bcrypt hashing, JWT HS256 tokens
|   |   |   +-- dependencies.py           # [DONE] get_current_user, get_db_session
|   |   |   +-- conversation_store.py     # [DONE] Persistent conversation CRUD + get_or_create_conversation (SQLite)
|   |   |   +-- seed.py                   # [DONE] Bootstrap admin user
|   |   |
|   |   +-- agents/
|   |   |   +-- analyst.py                # [DONE] SQL analyst agent loop
|   |   |   +-- orchestrator_planner.py   # [DONE] DAG task planner
|   |   |   +-- dag_executor.py           # [DONE] Parallel task executor
|   |   |   +-- quant_analyst.py          # [DONE] Statistical analysis agent
|   |   |   +-- deep_think.py             # [DONE] Dimension extraction + investigation
|   |   |   +-- response_generator.py     # [DONE] Multi-task response synthesizer
|   |   |   +-- clarifier.py              # [DONE] Ambiguity detection + clarification
|   |   |   +-- common.py                 # [DONE] Shared types (ChatChunk, AgentContext)
|   |   |   +-- tool_base.py             # [DONE] Tool ABC, ToolContext, ToolRegistry
|   |   |   +-- tools.py                  # [DONE] Core tools (4): RunSql, GetSchema, SearchSimilar, Clarify
|   |   |   +-- stat_tools.py             # [DONE] Statistical tools (6)
|   |   |   +-- advanced_tools.py         # [DONE] Advanced analytics tools (14)
|   |   |   +-- stats_resolver.py         # [DONE] Stats context resolution
|   |   |
|   |   +-- prompts/                      # 15 Jinja2 templates
|   |   |   +-- __init__.py               # [DONE] Jinja2 template loader
|   |   |   +-- analyst_system.j2         # [DONE] SQL analyst prompt
|   |   |   +-- statistician_system.j2    # [DONE] Statistician prompt
|   |   |   +-- quant_analyst_system.j2   # [DONE] Quant analyst prompt
|   |   |   +-- orchestrator_planner.j2   # [DONE] DAG planner prompt
|   |   |   +-- enrichment_evaluator.j2   # [DONE] Enrichment evaluation
|   |   |   +-- investigation_evaluator.j2 # [DONE] Investigation evaluation
|   |   |   +-- dimension_extractor.j2    # [DONE] 5W1H dimension extraction
|   |   |   +-- response_synthesizer.j2   # [DONE] Response synthesis
|   |   |   +-- insight_quality_gate.j2   # [DONE] Insight quality check
|   |   |   +-- investigation_synthesizer.j2 # [DONE] Investigation synthesis
|   |   |   +-- clarifier_system.j2       # [DONE] Clarification prompt
|   |   |   +-- nl_trigger.j2             # [DONE] NL trigger evaluation
|   |   |   +-- automation_namer.j2       # [DONE] Auto-name automations
|   |   |   +-- sql_generator.j2          # [DONE] NL → SQL for workflows
|   |   |   +-- title_generator.j2        # [DONE] Conversation title generation
|   |   |
|   |   +-- llm/
|   |   |   +-- __init__.py               # [DONE] Exports LLMProvider, LLMResponse, LLMChunk, ToolCall, create_llm
|   |   |   +-- base.py                   # [DONE] Protocol: LLMProvider, LLMResponse, ToolCall
|   |   |   +-- factory.py                # [DONE] Registry-based factory: create_llm(provider, settings)
|   |   |   +-- gemini.py                 # [DONE] Google Gemini (chat + stream + tools)
|   |   |   +-- ollama.py                 # [DONE] Ollama local models (chat + stream + tools, 120s timeout)
|   |   |   +-- vertex.py                 # [DONE] Google Vertex AI provider
|   |   |
|   |   +-- db/
|   |   |   +-- connector.py              # [DONE] SQLAlchemy wrapper (connect, execute, row limits, read_only mode)
|   |   |   +-- schema.py                 # [DONE] DDL introspection
|   |   |   +-- data_loader.py            # [DONE] CSV → SQLite loader
|   |   |   +-- stats_computer.py         # [DONE] Pre-computed dataset statistics
|   |   |   +-- migrations.py             # [DONE] Schema migrations
|   |   |
|   |   +-- rag/
|   |   |   +-- __init__.py               # [DONE] Exports VectorStoreBackend, ChromaVectorStore, VectorStore, InMemoryVectorStore
|   |   |   +-- base.py                   # [DONE] VectorStoreBackend protocol (@runtime_checkable)
|   |   |   +-- store.py                  # [DONE] ChromaVectorStore: 4 collections (qa, ddl, docs, findings)
|   |   |   +-- memory.py                 # [DONE] InMemoryVectorStore (difflib-based, for testing)
|   |   |
|   |   +-- memory/
|   |   |   +-- conversation_store.py     # [DONE] In-memory LRU + TTL conversation history
|   |   |
|   |   +-- admin/
|   |   |   +-- routes.py                 # [DONE] Admin endpoints (org config CRUD, client-config)
|   |   |   +-- config_store.py           # [DONE] JSON config file management (read/write/upsert/delete)
|   |   |   +-- models.py                 # [DONE] FeatureToggles, OrgConfig, OrgBranding, ClientConfig, ResolvedClientConfig
|   |   |
|   |   +-- observability/
|   |   |   +-- tracer.py                 # [STUB] Empty
|   |   |   +-- store.py                  # [STUB] Empty
|   |   |
|   |   +-- automations/
|   |   |   +-- routes.py                 # [DONE] Automation CRUD + run endpoints
|   |   |   +-- scheduler.py              # [DONE] APScheduler cron-based execution
|   |   |   +-- evaluator.py              # [DONE] SQL workflow executor + trigger evaluator
|   |   |   +-- nl_trigger.py             # [DONE] Natural-language trigger evaluation
|   |   |
|   |   +-- datasets/
|   |   |   +-- routes.py                 # [DONE] Dataset CRUD endpoints
|   |   |   +-- service.py                # [DONE] Dataset management service
|   |   |
|   |   +-- insights/
|   |   |   +-- routes.py                 # [DONE] Insight CRUD + bookmark endpoints
|   |   |
|   |   +-- training/
|   |       +-- trainer.py                # [DONE] RAG bootstrap (DDL + docs + 12 QA pairs)
|   |       +-- schema.py                 # [DONE] DDL constant (17-column transactions table)
|   |       +-- documentation.py          # [DONE] Business context & column descriptions
|   |       +-- queries.py                # [DONE] 12 example Q->SQL pairs (6 categories)
|   |
|   +-- tests/
|       +-- conftest.py                   # [DONE] Fixtures (in-memory DB, temp RAG, settings)
|       +-- test_agent.py                 # [DONE] Agent loop + tool execution + RAG training
|       +-- test_db.py                    # [DONE] Connector, queries, schema, error handling
|       +-- test_rag.py                   # [DONE] All 4 collections, search, dedup, distance
|
+-- frontend/
    +-- package.json                      # [DONE] Next.js 16, React 19
    +-- tsconfig.json                     # [DONE] TypeScript config
    +-- next.config.ts                    # [DONE] Next.js config with API rewrites
    +-- components.json                   # [DONE] Shadcn config (New York style)
    +-- playwright.config.ts              # [DONE] E2E testing
    |
    +-- src/
        +-- app/
        |   +-- layout.tsx                # [DONE] Root layout (fonts, health gate, toast)
        |   +-- page.tsx                  # [DONE] Home page (AuthGuard + AppShell + ChatPanel)
        |   +-- globals.css               # [DONE] Tailwind 4 + OKLch theme + glass utility
        |   +-- login/page.tsx            # [DONE] Login form
        |   +-- register/page.tsx         # [DONE] Registration form
        |   +-- admin/
        |       +-- layout.tsx            # [DONE] Admin layout with guards
        |       +-- page.tsx              # [DONE] Admin dashboard
        |       +-- automations/          # [DONE] Automation management
        |       +-- notifications/        # [DONE] Notification management
        |
        +-- components/
        |   +-- auth/auth-guard.tsx       # [DONE] Protected route wrapper
        |   +-- health/health-check-gate.tsx # [DONE] Backend health verification
        |   +-- chat/ (7 components)      # [DONE] ChatPanel, MessageList, MessageBubble,
        |   |                             #        MessageInput, MessageActions, WelcomeScreen, InputToolbar
        |   +-- chunks/ (15 components)   # [DONE] ChunkRenderer, AnswerChunk, SqlChunk,
        |   |                             #        ToolCallChunk, ToolResultChunk, StatusChunk, ErrorChunk,
        |   |                             #        ClarificationChunk, InsightChunk, StatsContextChunk,
        |   |                             #        ThinkingTrace, TraceModal, ChartBlock, DataTable, CitationLink
        |   +-- layout/ (6 components)    # [DONE] AppShell, Header, LeftSidebar, RightSidebar,
        |   |                             #        UserMenu, DatasetSelector
        |   +-- sidebar/ (5 components)   # [DONE] ConversationList, ConversationItem,
        |   |                             #        SearchResults, ProcessSteps, StepItem
        |   +-- sql/ (2 components)       # [DONE] SqlExecutor, ChartConfigurator
        |   +-- insights/ (5 components)  # [DONE] InsightBell, InsightPopover, InsightCard, InsightAllModal
        |   +-- automations/ (14 components) # [DONE] WorkflowBuilder, WorkflowCanvas, AutomationList,
        |   |                             #        AutomationCard, SqlBlockNode, TriggerConditionBuilder, etc.
        |   +-- notifications/ (7 components) # [DONE] NotificationBell, NotificationPopover, etc.
        |   +-- dataset/dataset-viewer.tsx # [DONE] Schema browser + sample data
        |   +-- sample-questions/         # [DONE] SampleQuestionsModal
        |   +-- admin/ (5 components)     # [DONE] FeatureToggles, BrandingEditor, UserOrgMappings,
        |   |                             #        AdminDomainEditor, ConversationViewer
        |   +-- ui/ (30+ components)      # [DONE] shadcn/Radix component library
        |
        +-- hooks/ (7 hooks)
        |   +-- use-sse-chat.ts           # [DONE] SSE streaming + agent step tracking
        |   +-- use-client-config.ts      # [DONE] Org config + feature flags
        |   +-- use-health-check.ts       # [DONE] Backend health polling
        |   +-- use-theme.ts              # [DONE] Dark/light mode toggle
        |   +-- use-syntax-theme.ts       # [DONE] Code highlighting theme
        |   +-- use-auto-scroll.ts        # [DONE] Auto-scroll to bottom
        |   +-- use-media-query.ts        # [DONE] Responsive breakpoint detection
        |
        +-- lib/ (11 utilities)
        |   +-- api.ts                    # [DONE] Fetch wrapper with credentials
        |   +-- sse-client.ts             # [DONE] SSE fetch + microtask batching
        |   +-- chunk-parser.ts           # [DONE] Parse ChatChunk + ToolResult
        |   +-- chart-detector.ts         # [DONE] Auto-detect chart type
        |   +-- sql-utils.ts              # [DONE] Table extraction for workflow edges
        |   +-- automation-utils.ts       # [DONE] Automation helpers
        |   +-- export-report.ts          # [DONE] PDF/CSV export
        |   +-- sample-questions.ts       # [DONE] Sample question data
        |   +-- model-utils.ts            # [DONE] Model name formatting
        |   +-- constants.ts              # [DONE] API URL, suggested questions
        |   +-- utils.ts                  # [DONE] cn() class merge utility
        |
        +-- stores/ (7 stores)
        |   +-- auth-store.ts             # [DONE] Auth (login, register, logout)
        |   +-- chat-store.ts             # [DONE] Chat (conversations, streaming, steps)
        |   +-- settings-store.ts         # [DONE] Settings (provider, model, agent mode)
        |   +-- client-config-store.ts    # [DONE] Org config (features, branding)
        |   +-- insight-store.ts          # [DONE] Insights (fetch, bookmark, delete)
        |   +-- automation-store.ts       # [DONE] Automations (CRUD, workflow builder)
        |   +-- notification-store.ts     # [DONE] Notifications (fetch, read, count)
        |
        +-- types/ (5 type files)
            +-- chat.ts                   # [DONE] ChatChunk, Message, Conversation, AgentStep,
            |                             #        OrchestratorPlan, AgentTrace, EnrichmentTrace
            +-- admin.ts                  # [DONE] FeatureToggles, OrgConfig, Branding
            +-- api.ts                    # [DONE] QueryResult, QueryError
            +-- automation.ts             # [DONE] Automation, AutomationRun, TriggerCondition, Workflow
            +-- insight.ts               # [DONE] Insight
```

### Dependencies

**Backend (from pyproject.toml):**

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.115.0 | HTTP framework |
| uvicorn[standard] | >=0.30.0 | ASGI server |
| sqlalchemy | >=2.0 | Database abstraction |
| chromadb | >=0.5.0 | Vector store |
| google-genai | >=1.0.0 | Gemini LLM |
| ollama | >=0.4.0 | Local LLM (dev) |
| pydantic-settings | >=2.0 | Config management |
| python-dotenv | >=1.0 | .env loading |
| sse-starlette | >=2.0 | SSE streaming |
| bcrypt | >=4.0 | Password hashing |
| python-jose[cryptography] | >=3.3 | JWT handling |

Dev: pytest >=8.0, pytest-asyncio >=0.24, httpx >=0.27

**Frontend (from package.json):**

| Package | Version | Purpose |
|---------|---------|---------|
| next | 16.1.6 | React framework |
| react | 19.2.3 | UI library |
| zustand | 5.0.11 | State management |
| radix-ui | 1.4.3 | Accessible UI primitives |
| framer-motion | 12.34.0 | Animation |
| recharts | 2.15.4 | Charting |
| react-markdown | 10.1.0 | Markdown rendering |
| react-syntax-highlighter | 16.1.0 | Code highlighting |
| tailwindcss | 4 | Styling |

---

## 16. Implementation Status Summary

> **Update (Mar 2):** All previously planned items except observability have been implemented. See `docs/` for current comprehensive documentation.

| Component | Status | File(s) |
|-----------|--------|---------|
| **Agent Pipeline** | | |
| Analyst Agent (with error recovery) | [DONE] | `agents/analyst.py` |
| Orchestrator Planner (DAG) | [DONE] | `agents/orchestrator_planner.py` |
| DAG Executor (parallel tasks) | [DONE] | `agents/dag_executor.py` |
| Quant Analyst Agent | [DONE] | `agents/quant_analyst.py` |
| Deep Think Pipeline | [DONE] | `agents/deep_think.py` |
| Response Synthesizer | [DONE] | `agents/response_generator.py` |
| Clarifier Agent | [DONE] | `agents/clarifier.py` |
| Tool ABC + ToolRegistry | [DONE] | `agents/tool_base.py`, `agents/tools.py` |
| Statistical Tools (6) | [DONE] | `agents/stat_tools.py` |
| Advanced Tools (14) | [DONE] | `agents/advanced_tools.py` |
| **LLM** | | |
| Gemini LLM Provider | [DONE] | `llm/gemini.py` |
| Ollama LLM Provider | [DONE] | `llm/ollama.py` |
| Vertex AI LLM Provider | [DONE] | `llm/vertex.py` |
| LLM Protocol + Factory | [DONE] | `llm/base.py`, `llm/factory.py` |
| Runtime LLM Switching | [DONE] | `api/routes.py` |
| **Prompts** | | |
| 15 Jinja2 Templates | [DONE] | `prompts/*.j2` |
| **Data** | | |
| Database Layer | [DONE] | `db/connector.py`, `db/schema.py` |
| SQL Executor (dual read-only) | [DONE] | `api/routes.py`, `db/connector.py` |
| Stats Computer | [DONE] | `db/stats_computer.py` |
| Data Loader | [DONE] | `db/data_loader.py` |
| Migrations | [DONE] | `db/migrations.py` |
| Data Generator | [DONE] | `generate_data.py` |
| **RAG & Memory** | | |
| RAG Store (ChromaDB, 4 collections) | [DONE] | `rag/store.py` |
| RAG Protocol + In-Memory | [DONE] | `rag/base.py`, `rag/memory.py` |
| Training Bootstrap | [DONE] | `training/trainer.py` |
| Dual Conversation Store | [DONE] | `memory/conversation_store.py`, `auth/conversation_store.py` |
| **Auth & Admin** | | |
| Authentication (JWT + bcrypt) | [DONE] | `auth/` |
| Admin System (9 toggles, branding) | [DONE] | `admin/` |
| Org Permissions | [DONE] | `auth/permissions.py` |
| **Features** | | |
| Automations (scheduler, triggers, notifications) | [DONE] | `automations/` |
| Insights (auto-generated, quality gate) | [DONE] | `insights/` |
| Datasets (upload, schema, stats) | [DONE] | `datasets/` |
| API Endpoints (50+) | [DONE] | `api/routes.py` + feature routers |
| Config | [DONE] | `config.py` |
| Tests | [DONE] | `tests/` |
| **Frontend** | | |
| Auth (login, register, guard) | [DONE] | `auth/`, `auth-store.ts` |
| Chat UI (7 components) | [DONE] | `components/chat/` |
| Chunk Renderers (15 components) | [DONE] | `components/chunks/` |
| Layout (6 components) | [DONE] | `components/layout/` |
| Sidebars (5 components) | [DONE] | `components/sidebar/` |
| SQL Executor + Chart Configurator | [DONE] | `components/sql/` |
| Insights UI (5 components) | [DONE] | `components/insights/` |
| Automations UI (14 components) | [DONE] | `components/automations/` |
| Notifications UI (7 components) | [DONE] | `components/notifications/` |
| Dataset Viewer + Selector | [DONE] | `components/dataset/`, `components/layout/` |
| SSE Client + 7 Hooks | [DONE] | `hooks/` |
| State Management (7 Zustand stores) | [DONE] | `stores/` |
| Admin Panel (3 pages, 5 components) | [DONE] | `app/admin/`, `components/admin/` |
| **Not Implemented** | | |
| Observability Dashboard | [STUB] | `observability/tracer.py`, `observability/store.py` |

---

## 17. Build Plan (Feb 13 -> Feb 28) — Historical

> **Note:** This build plan was the original sprint schedule. The project significantly exceeded these milestones, implementing features originally planned for post-hackathon (automations, insights, multi-dataset support, workflow builder, deep think mode). See `docs/progress-report.md` for the actual timeline.

### Division of Work

| Owner | Focus |
|-------|-------|
| **Nachiket** | System architecture, multi-agent pipeline, LLM prompt engineering, observability, frontend |
| **Arush** | Data layer, SQL execution, API endpoints, training data, testing |

### Sprint 1: Core Engine (Feb 13-18)

**Goal:** From-scratch backend replaces Vanna, handles all 6 query categories. Frontend chat UI working.

| Day | Task | Owner | Status |
|-----|------|-------|--------|
| Feb 13-14 | Port sql-agent into InsightXpert repo structure. Wire up generate_data.py + existing training data. Get single-agent analyst working with Gemini against the 250K dataset. Build frontend chat UI with SSE streaming. Auth system. SQL executor. Model selector. | Nachiket | [DONE] |
| Feb 13-14 | Expand example Q&A pairs from 12 to 25+ (cover more edge cases: multi-part questions, temporal ranges, null handling). Test SQL accuracy against all 6 categories. | Arush | In progress (12 of 25+) |
| Feb 15-16 | Implement statistician agent (pure Python: rate comparisons, benchmarks, sample size checks). Implement creative narrator prompt (layered response structure). Wire orchestrator pipeline. | Nachiket | Next |
| Feb 15-16 | Add ambiguity detection (too vague -> clarify). Add conversation context (follow-up questions reuse prior SQL context). | Arush | Next |
| Feb 17-18 | Observability: tracer + obs.db storage. Instrument analyst, statistician, narrator with spans. | Nachiket | |
| Feb 17-18 | Integration testing: run all 25+ example queries end-to-end, verify accuracy. Fix edge cases. | Arush | |

**Checkpoint:** Backend handles diverse queries with multi-agent pipeline. Accuracy verified.

### Sprint 2: Polish + Dashboard (Feb 19-25)

| Day | Task | Owner |
|-----|------|-------|
| Feb 19-20 | Chat UI polish: agent step indicators, chart rendering, responsive mobile layout. | Nachiket |
| Feb 19-20 | API hardening: error handling, timeout safety, graceful degradation. Add /obs/* endpoints. | Arush |
| Feb 21-22 | Dashboard: trace waterfall, query history, agent latency breakdown. | Nachiket |
| Feb 21-22 | Dashboard backend: obs API routes, aggregation queries. | Arush |
| Feb 23-24 | Anomaly detector (background task: scans tables, stores findings in RAG). Follow-up suggestions in responses. | Nachiket |
| Feb 23-24 | End-to-end testing with full frontend. Fix UX issues. | Arush |
| Feb 25 | Final integration, README, setup instructions, sample query set (15+ diverse). | Both |

### Sprint 3: Submission + Presentation Prep (Feb 26-Mar 8)

| Day | Task | Owner |
|-----|------|-------|
| Feb 26-27 | Record 3-5 min video demo. Package submission. | Both |
| Feb 28 | **Submit.** | Both |
| Mar 1-7 | 10-min pitch deck. Rehearse demo and Q&A. | Both |
| Mar 8 | **Final presentation.** | Both |

---

## 18. Scoring Strategy

Map every architecture decision to the evaluation rubric:

### Insight Accuracy (30%) — highest weight
- **Multi-step reasoning**: Analyst runs SQL -> Statistician validates + enriches -> catches errors before presenting
- **RAG few-shot**: 25+ example Q&A pairs guide accurate SQL generation
- **Cross-verification**: Statistician compares results to baselines, flags anomalies

### Query Understanding (25%)
- **Ambiguity detection**: System asks clarifying questions instead of guessing
- **Multi-part queries**: Agent loop handles compound questions (tool calling allows multiple SQL executions)
- **All 6 categories covered**: Descriptive, comparative, temporal, segmentation, correlation, risk

### Explainability (20%)
- **Layered responses**: Direct answer -> evidence -> provenance -> caveats -> follow-ups
- **Business vocabulary**: Creative narrator translates SQL columns to business terms
- **Data provenance**: Every response includes scope (row count, time range)
- **Confidence caveats**: Small samples flagged automatically by statistician

### Conversational Quality (15%)
- **Follow-up context**: Conversation history maintained across turns (dual-store memory)
- **Ambiguity handling**: Asks clarifying questions when needed
- **Follow-up suggestions**: Proactive next-question recommendations
- **Streaming**: Real-time SSE so users see progress, not a loading spinner

### Innovation & Technical Implementation (10%)
- **Multi-agent architecture**: Analyst + Statistician + Narrator pipeline (novel for a hackathon)
- **Live observability dashboard**: Judges can see the agent reasoning in real-time
- **Background anomaly detector**: Proactive insights without user asking
- **From-scratch engine**: No black-box framework dependency
- **SSE streaming with agent step visibility**: Users see which agent is working and what it's doing
- **Runtime LLM switching**: Hot-swap between Gemini and Ollama without restart
- **SQL Executor**: Direct database access for power users

---

## 19. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gemini generates incorrect SQL | High (30% of score) | 25+ few-shot examples in RAG, statistician cross-checks results, error recovery loop |
| Multi-agent adds latency | Medium | Statistician is pure Python (no LLM call), narrator is one LLM call. Total: 2 LLM calls per question (analyst + narrator). |
| Ambiguity detection over-triggers | Low | Conservative threshold — only trigger for genuinely vague queries ("tell me about data"). Default to attempting an answer. |
| ChromaDB embedding quality | Low | 25+ hand-crafted Q&A pairs provide strong few-shot matches. DDL + documentation always available as fallback. |
| Auth session expiry mid-conversation | Low | 24-hour token expiry. Frontend checks auth on route changes. |

---

## 20. What This Architecture Enables Post-Hackathon

The same architecture, with minimal changes, scales to a real fintech platform:

| Hackathon (now) | Production (later) |
|-----------------|-------------------|
| SQLite data DB | PostgreSQL / any SQLAlchemy-supported DB |
| SQLite auth DB | PostgreSQL with proper migrations |
| SQLite obs DB | PostgreSQL with monthly partitions + 365-day retention |
| Single Gemini model | Model routing (Gemini for complex, Ollama for simple) |
| 250K static rows | Live ingestion, real transaction data |
| Background anomaly scan | Scheduled cron + alerting (Slack/email) |
| JWT cookie auth | OAuth 2.0 + RBAC + audit logging |
| Embedded ChromaDB | Managed vector DB (Pinecone, Weaviate) |
| In-memory conversation store | Redis / PostgreSQL persistent store |
| Single admin user | Multi-tenant user management |

The from-scratch approach means nothing needs to be ripped out — just swapped and scaled.
