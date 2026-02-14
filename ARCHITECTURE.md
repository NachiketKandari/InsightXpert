# InsightXpert — Architecture & Technical Vision

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

## 2. Current State (as of Feb 14)

The from-scratch engine has replaced Vanna and is fully ported. The single-agent analyst pipeline is working end-to-end. The frontend chat UI with SSE streaming is fully implemented. Authentication, persistent conversations, runtime LLM switching, and a SQL executor are all operational.

### Implemented
- **Analyst agent** (`agents/analyst.py`) — Full tool-calling loop: RAG retrieval -> LLM -> tool execution (run_sql, get_schema, search_similar) -> streaming response
- **Tool framework** (`agents/tools.py`) — 3 tools defined as JSON schemas with async execution routing
- **LLM providers** (`llm/gemini.py`, `llm/ollama.py`) — Both Gemini and Ollama working with tool calling, streaming, and message conversion
- **Runtime LLM switching** — `/api/config/switch` endpoint hot-swaps the LLM provider and model without restart
- **RAG store** (`rag/store.py`) — ChromaDB with 4 collections (qa_pairs, ddl, docs, findings), semantic search, auto-deduplication via SHA256 IDs
- **Database layer** (`db/connector.py`, `db/schema.py`) — SQLAlchemy wrapper with row limits, timeouts, schema introspection
- **Training bootstrap** (`training/trainer.py`) — Auto-loads DDL, documentation, 12 example Q&A pairs into RAG on startup
- **Conversation memory** — Dual-store: in-memory LRU for LLM context + SQLite-backed persistent store for conversation history
- **Authentication** (`auth/`) — JWT (HS256) + bcrypt password hashing + HttpOnly cookie sessions. Default admin user auto-seeded on startup
- **API** (`api/routes.py`) — 15 endpoints: chat (SSE), chat/poll, train, schema, health, config, config/switch, sql/execute, auth (login/logout/me), conversations CRUD
- **SQL Executor** — `POST /api/sql/execute` with regex-based write blocker (blocks INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, etc.)
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

### Not Yet Implemented (stubs or planned)
- **Orchestrator** (`agents/orchestrator.py`) — 6-line stub, no multi-agent routing
- **Statistician agent** — File does not exist yet
- **Creative Narrator agent** — File does not exist yet
- **Anomaly Detector** — File does not exist yet
- **Observability** (`observability/tracer.py`, `observability/store.py`) — Empty stubs, no tracing or obs.db
- **Obs API routes** (`api/obs_routes.py`) — File does not exist yet
- **Dashboard pages** — Not started (live trace, query history, agent performance)
- **Ambiguity detection** — Not implemented; analyst handles all queries directly

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
|  |   Chat UI     |  |   Dashboard   |  |   SQL Executor         | |
|  |   (SSE)       |  |   [PLANNED]   |  |   [DONE]               | |
|  |   [DONE]      |  |   (polling)   |  |   (Sheet panel)        | |
|  +------+--------+  +-------+-------+  +----------+-------------+ |
|         |                    |                     |               |
|  +------+--------+  +-------+-------+  +----------+-------------+ |
|  |   Auth Flow   |  |  Model Select |  |   Training Admin       | |
|  |   [DONE]      |  |  [DONE]       |  |   [PLANNED]            | |
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
|  GET  /api/schema     [DONE]    GET /api/obs/*      [PLANNED]    |
|  GET  /api/health     [DONE]                                     |
|  POST /api/auth/login [DONE]    GET /api/conversations [DONE]    |
|  POST /api/auth/logout[DONE]    CRUD /api/conversations/ [DONE]  |
|  GET  /api/auth/me    [DONE]                                     |
|                                                                   |
|  +-------------------------------------------------------------+ |
|  |                    Orchestrator [STUB]                        | |
|  |                                                              | |
|  |  +-----------+  +---------------+  +----------------------+  | |
|  |  | Analyst   |->| Statistician  |->| Creative Narrator    |  | |
|  |  | [DONE]    |  | [PLANNED]     |  | [PLANNED]            |  | |
|  |  +-----------+  +---------------+  +----------------------+  | |
|  |                                                              | |
|  |  +--------------------------------------------------------+  | |
|  |  | Anomaly Detector (background) [PLANNED]                |  | |
|  |  +--------------------------------------------------------+  | |
|  +-------------------------------------------------------------+ |
|                                                                   |
|  +-----------+  +-----------+  +-----------+  +----------------+ |
|  | LLM       |  | RAG       |  | SQLite    |  | Observability  | |
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
   +-- Send messages + tool definitions to LLM
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

**System prompt structure:**
- Identity as InsightXpert AI data analyst
- Full DDL for the transactions table (17 columns)
- Business documentation (column descriptions, domain rules)
- 7 domain rules (SELECT only, NULL handling, fraud_flag semantics, ROUND(2), correlation != causation, small sample flags, execute before answering)
- 5-layer response structure requirement
- RAG context dynamically injected per query

### 5.2 Tool Framework

**File:** `agents/tools.py`

Three tools exposed to the LLM as JSON Schema function definitions:

| Tool | Purpose | Arguments | Returns |
|------|---------|-----------|---------|
| `run_sql` | Execute SELECT query on SQLite | `sql: string` | `{rows: [...], row_count: N}` |
| `get_schema` | Get CREATE TABLE DDL | `tables?: string[]` | DDL string or table info JSON |
| `search_similar` | Search ChromaDB knowledge base | `query: string, collection: "qa_pairs"\|"ddl"\|"docs"` | Array of `{document, metadata, distance}` |

The `execute_tool()` function routes by tool name, handles errors with tracebacks, and enforces row limits on SQL results.

### 5.3 LLM Provider Abstraction

**Files:** `llm/base.py`, `llm/gemini.py`, `llm/ollama.py`

```python
class LLMProvider(Protocol):
    async def chat(messages, tools) -> LLMResponse       # Non-streaming
    async def chat_stream(messages, tools) -> AsyncGenerator[LLMChunk]  # Streaming

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

**Gemini provider** — Uses `google-genai` async client. Converts internal message format to Gemini's `Content`/`Part` types. Maps tool definitions to `FunctionDeclaration`. Handles function_call responses and multipart content.

**Ollama provider** — Uses `ollama` async client. Same protocol, different wire format. Fallback for local development without API keys.

**Runtime switching** — Provider can be changed at runtime via `POST /api/config/switch`. The endpoint instantiates a new provider and replaces `app.state.llm`. No restart needed. Available models are served from `GET /api/config` (Gemini models are hardcoded, Ollama models are dynamically queried from the local server).

### 5.4 Planned Multi-Agent Pipeline

**File:** `agents/orchestrator.py` (6-line stub)

The orchestrator will route questions through a pipeline of specialized agents:

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
| **Analyst** [DONE] | NL->SQL, execute queries, return raw results | Yes (Gemini) | `run_sql`, `get_schema`, `search_similar` |
| **Statistician** [PLANNED] | Analyze result sets: distributions, outliers, trends, benchmark comparisons | No (pure Python) | `compute_stats` (in-process) |
| **Creative Narrator** [PLANNED] | Generate leadership-friendly response with layered structure | Yes (Gemini) | None (pure LLM generation) |
| **Anomaly Detector** [PLANNED] | Background scan: sample tables, flag unusual patterns, store in RAG | Yes (Gemini) | `run_sql`, `add_finding` |

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
| Zustand | 5.0.11 | State management (3 stores) |
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

- **Header:** Logo + Model selector (Provider / Model dropdowns with chevrons) + SQL Executor button + user email + logout button
- **Left sidebar:** Conversation history list with create/delete/rename. Collapsible on desktop, Sheet on mobile
- **Right sidebar:** Real-time agent process steps timeline. Shows each step's status (pending/running/done/error)
- **Chat panel:** Message list with auto-scroll, chunk-by-chunk rendering, message input with suggested questions on welcome

### 7.3 State Management (3 Zustand Stores)

**`stores/auth-store.ts`**
```
State: user | null, isLoading, error
Actions: login(email, password), logout(), checkAuth()
```

**`stores/chat-store.ts`**
```
State: conversations[], activeConversationId, isStreaming, agentSteps[], sidebarOpen flags
Actions: newConversation(), addUserMessage(), appendChunk(), finishStreaming(),
         deleteConversation(), renameConversation(), addAgentStep(), updateAgentStep()
Persistence: Fetches from /api/conversations on init, CRUD via REST API
```

**`stores/settings-store.ts`**
```
State: currentProvider, currentModel, providers[], loading
Actions: fetchConfig() [GET /api/config], switchModel(provider, model) [POST /api/config/switch]
         Optimistic updates with rollback on failure
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
- `execute(sql, row_limit=1000, timeout=30)` — Execute SQL, return JSON-serializable rows, enforce row limit
- `get_tables()` — Introspect table names
- `disconnect()` — Dispose engine

### 8.2 Schema Introspection

**File:** `db/schema.py`

- `get_table_info(engine, table_name)` -> dict with columns, types, keys, foreign keys
- `get_schema_ddl(engine)` -> Full CREATE TABLE DDL for all tables

### 8.3 SQL Executor Endpoint

**File:** `api/routes.py` — `POST /api/sql/execute`

Server-side safety guard using compiled regex:

```python
_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|
         GRANT|REVOKE|ATTACH|DETACH|PRAGMA\s+\w+\s*=)\b",
    re.IGNORECASE,
)
```

Returns 403 with a descriptive error if any write operation is detected. Otherwise executes the query with the configured `sql_row_limit` and `sql_timeout_seconds`, returning `{columns, rows, row_count, execution_time_ms}`.

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

**File:** `rag/store.py`

ChromaDB embedded persistent client with 4 collections:

| Collection | Content | Search Method | Default N |
|-----------|---------|---------------|-----------|
| `qa_pairs` | Question->SQL pairs (hand-crafted + auto-learned) | `search_qa()` | 5 |
| `ddl` | Table DDL and schema | `search_ddl()` | 3 |
| `docs` | Business documentation and guidelines | `search_docs()` | 3 |
| `findings` | Anomaly findings from background analysis | `search_findings()` | 3 |

**Auto-deduplication:** Document IDs are SHA256 hashes of content (first 16 chars). Upserts prevent duplicates.

**Auto-learning:** When the analyst successfully generates SQL, the question->SQL pair is automatically saved to the `qa_pairs` collection, improving future retrieval.

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
- Tables: `conversations`, `messages`
- Features: Full CRUD, message chunks JSON storage, user_id isolation
- Frontend loads conversation list on init via `GET /api/conversations`

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
| GET | `/api/health` | No | — | `{status: "ok", timestamp}` | Health check |

**ChatChunk types:** `status`, `sql`, `tool_call`, `tool_result`, `answer`, `error`

### Planned

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/obs/traces` | List recent traces |
| GET | `/api/obs/traces/{id}` | Single trace with spans |
| GET | `/api/obs/stats` | Aggregate agent/LLM metrics |

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

## 13. Observability & Dashboard (PLANNED)

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
|   |   |   +-- routes.py                 # [DONE] 15 endpoints (chat, auth, config, sql, conv CRUD)
|   |   |   +-- models.py                 # [DONE] Pydantic models for all endpoints
|   |   |   +-- obs_routes.py             # [PLANNED] /obs/traces, /obs/spans, /obs/stats
|   |   |
|   |   +-- auth/
|   |   |   +-- routes.py                 # [DONE] Login, logout, me endpoints
|   |   |   +-- models.py                 # [DONE] User, ConversationRecord, MessageRecord ORM
|   |   |   +-- security.py               # [DONE] bcrypt hashing, JWT HS256 tokens
|   |   |   +-- dependencies.py           # [DONE] get_current_user, get_db_session
|   |   |   +-- conversation_store.py     # [DONE] Persistent conversation CRUD (SQLite)
|   |   |   +-- seed.py                   # [DONE] Bootstrap admin user
|   |   |
|   |   +-- agents/
|   |   |   +-- analyst.py                # [DONE] Full agent loop (RAG + LLM + tools)
|   |   |   +-- tools.py                  # [DONE] 3 tools: run_sql, get_schema, search_similar
|   |   |   +-- orchestrator.py           # [STUB] (6 lines, no routing logic)
|   |   |   +-- statistician.py           # [PLANNED] Pure Python stats/comparisons
|   |   |   +-- narrator.py               # [PLANNED] LLM-powered narrator
|   |   |   +-- anomaly_detector.py       # [PLANNED] Background scan
|   |   |
|   |   +-- llm/
|   |   |   +-- base.py                   # [DONE] Protocol: LLMProvider, LLMResponse, ToolCall
|   |   |   +-- gemini.py                 # [DONE] Google Gemini (chat + stream + tools)
|   |   |   +-- ollama.py                 # [DONE] Ollama local models (chat + stream + tools)
|   |   |
|   |   +-- db/
|   |   |   +-- connector.py              # [DONE] SQLAlchemy wrapper (connect, execute, row limits)
|   |   |   +-- schema.py                 # [DONE] DDL introspection
|   |   |
|   |   +-- rag/
|   |   |   +-- store.py                  # [DONE] ChromaDB: 4 collections (qa, ddl, docs, findings)
|   |   |
|   |   +-- memory/
|   |   |   +-- conversation_store.py     # [DONE] In-memory LRU + TTL conversation history
|   |   |
|   |   +-- observability/
|   |   |   +-- tracer.py                 # [STUB] Empty
|   |   |   +-- store.py                  # [STUB] Empty
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
    +-- package.json                      # [DONE] Next.js 16.1.6, React 19.2.3
    +-- tsconfig.json                     # [DONE] TypeScript config
    +-- next.config.ts                    # [DONE] Next.js config with API rewrites
    +-- components.json                   # [DONE] Shadcn config (New York style)
    |
    +-- src/
        +-- app/
        |   +-- layout.tsx                # [DONE] Root layout (fonts, TooltipProvider)
        |   +-- page.tsx                  # [DONE] Home page (AuthGuard + AppShell + ChatPanel)
        |   +-- login/
        |   |   +-- page.tsx              # [DONE] Login form
        |   +-- globals.css               # [DONE] Tailwind 4 + OKLch theme + glass utility
        |
        +-- components/
        |   +-- auth/
        |   |   +-- auth-guard.tsx        # [DONE] Protected route wrapper
        |   |
        |   +-- chat/
        |   |   +-- chat-panel.tsx        # [DONE] Main chat interface orchestrator
        |   |   +-- message-bubble.tsx    # [DONE] User/assistant message rendering
        |   |   +-- message-input.tsx     # [DONE] Textarea with send/stop buttons
        |   |   +-- message-list.tsx      # [DONE] Scrollable message list + auto-scroll
        |   |   +-- welcome-screen.tsx    # [DONE] Landing with 6 suggested questions
        |   |
        |   +-- chunks/
        |   |   +-- chunk-renderer.tsx    # [DONE] Route chunk to correct renderer
        |   |   +-- status-chunk.tsx      # [DONE] Loading indicator
        |   |   +-- tool-call-chunk.tsx   # [DONE] Tool call display
        |   |   +-- sql-chunk.tsx         # [DONE] SQL syntax highlighting + copy
        |   |   +-- tool-result-chunk.tsx # [DONE] Data table + chart display
        |   |   +-- answer-chunk.tsx      # [DONE] Markdown answer rendering
        |   |   +-- error-chunk.tsx       # [DONE] Error display
        |   |   +-- chart-block.tsx       # [DONE] Auto-detected bar/pie/line charts
        |   |   +-- data-table.tsx        # [DONE] Result table component
        |   |
        |   +-- layout/
        |   |   +-- app-shell.tsx         # [DONE] 3-column layout with Framer Motion
        |   |   +-- header.tsx            # [DONE] Logo + model selector + SQL + auth
        |   |   +-- left-sidebar.tsx      # [DONE] Conversation history
        |   |   +-- right-sidebar.tsx     # [DONE] Agent process steps
        |   |   +-- model-selector.tsx    # [DONE] Provider/model dropdown
        |   |
        |   +-- sidebar/
        |   |   +-- conversation-item.tsx # [DONE] Single conversation (rename/delete)
        |   |   +-- conversation-list.tsx # [DONE] Conversation list
        |   |   +-- process-steps.tsx     # [DONE] Agent step timeline
        |   |   +-- step-item.tsx         # [DONE] Single step indicator
        |   |
        |   +-- sql/
        |   |   +-- sql-executor.tsx      # [DONE] SQL editor + execution panel
        |   |
        |   +-- ui/                       # [DONE] 13 shadcn/Radix components
        |       +-- badge, button, card, chart, collapsible,
        |       +-- dropdown-menu, input, scroll-area, separator,
        |       +-- sheet, skeleton, textarea, tooltip
        |
        +-- hooks/
        |   +-- use-sse-chat.ts           # [DONE] SSE streaming + agent step tracking
        |   +-- use-auto-scroll.ts        # [DONE] Auto-scroll to bottom
        |   +-- use-media-query.ts        # [DONE] Responsive breakpoint detection
        |
        +-- lib/
        |   +-- api.ts                    # [DONE] Fetch wrapper with credentials
        |   +-- sse-client.ts             # [DONE] SSE fetch + line buffering
        |   +-- chunk-parser.ts           # [DONE] Parse ChatChunk + ToolResult
        |   +-- chart-detector.ts         # [DONE] Auto-detect chart type from data
        |   +-- constants.ts              # [DONE] API URL, suggested questions, chunk types
        |   +-- utils.ts                  # [DONE] cn() class merge utility
        |
        +-- stores/
        |   +-- auth-store.ts             # [DONE] Zustand auth state (login/logout/check)
        |   +-- chat-store.ts             # [DONE] Zustand chat state (messages, steps, sidebar)
        |   +-- settings-store.ts         # [DONE] Zustand settings (provider/model selection)
        |
        +-- types/
            +-- chat.ts                   # [DONE] ChatChunk, Message, Conversation, AgentStep
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

| Component | Status | File(s) |
|-----------|--------|---------|
| Analyst Agent | [DONE] | `agents/analyst.py` |
| Tool Framework | [DONE] | `agents/tools.py` |
| Gemini LLM Provider | [DONE] | `llm/gemini.py` |
| Ollama LLM Provider | [DONE] | `llm/ollama.py` |
| LLM Protocol | [DONE] | `llm/base.py` |
| Runtime LLM Switching | [DONE] | `api/routes.py` (config endpoints) |
| Database Layer | [DONE] | `db/connector.py`, `db/schema.py` |
| SQL Executor (read-only) | [DONE] | `api/routes.py` (sql/execute endpoint) |
| RAG Store | [DONE] | `rag/store.py` |
| Training Bootstrap | [DONE] | `training/trainer.py` |
| In-Memory Conversation Store | [DONE] | `memory/conversation_store.py` |
| Persistent Conversation Store | [DONE] | `auth/conversation_store.py` |
| Authentication (JWT + bcrypt) | [DONE] | `auth/` (routes, security, dependencies, models, seed) |
| API Endpoints | [DONE] | `api/routes.py` (15 endpoints) |
| API Models | [DONE] | `api/models.py` |
| Config | [DONE] | `config.py` |
| Data Generator | [DONE] | `generate_data.py` |
| Tests | [DONE] | `tests/` (3 files) |
| Frontend Auth (login, guard) | [DONE] | `auth-guard.tsx`, `auth-store.ts`, `login/page.tsx` |
| Frontend Chat UI | [DONE] | `components/chat/` (5 files) |
| Frontend Chunks + Charts | [DONE] | `components/chunks/` (9 files) |
| Frontend Layout | [DONE] | `components/layout/` (5 files) |
| Frontend Sidebars | [DONE] | `components/sidebar/` (4 files) |
| Frontend Model Selector | [DONE] | `components/layout/model-selector.tsx`, `settings-store.ts` |
| Frontend SQL Executor | [DONE] | `components/sql/sql-executor.tsx` |
| SSE Client | [DONE] | `hooks/use-sse-chat.ts` |
| State Management | [DONE] | `stores/` (3 stores: auth, chat, settings) |
| Orchestrator | [STUB] | `agents/orchestrator.py` (6 lines) |
| Statistician Agent | [PLANNED] | — |
| Narrator Agent | [PLANNED] | — |
| Anomaly Detector | [PLANNED] | — |
| Observability | [STUB] | `observability/tracer.py`, `observability/store.py` |
| Dashboard Pages | [PLANNED] | — |

---

## 17. Build Plan (Feb 13 -> Feb 28)

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
