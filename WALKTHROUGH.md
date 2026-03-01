# InsightXpert — Complete Project Walkthrough

> A consolidated reading guide covering everything in the codebase.
> Designed to be read on a flight — no code access needed.

---

## Table of Contents

1. [What Is InsightXpert?](#1-what-is-insightxpert)
2. [The Problem It Solves](#2-the-problem-it-solves)
3. [How It Works (End-to-End)](#3-how-it-works-end-to-end)
4. [Backend Architecture](#4-backend-architecture)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Database & Data](#6-database--data)
7. [RAG & Memory Systems](#7-rag--memory-systems)
8. [Authentication & Admin](#8-authentication--admin)
9. [API Reference](#9-api-reference)
10. [Deployment & Infrastructure](#10-deployment--infrastructure)
11. [Design Patterns & Decisions](#11-design-patterns--decisions)
12. [Testing](#12-testing)
13. [What's Implemented vs Planned](#13-whats-implemented-vs-planned)
14. [File Map](#14-file-map)

---

## 1. What Is InsightXpert?

InsightXpert is a conversational AI data analyst built for the **Techfest 2025-26 Leadership Analytics Challenge** at IIT Bombay. It lets non-technical business leaders ask natural language questions about 250,000 synthetic Indian digital payment transactions and get accurate, well-explained, data-backed answers — without writing SQL.

**Live at:** https://insightxpert-ai.web.app

**Team:**
- **Nachiket** — System architecture, UI/UX, LLM pipeline, prompt engineering
- **Arush** — Data layer, SQL execution, API endpoints, deployment

---

## 2. The Problem It Solves

Product managers, operations heads, and risk officers need insights from payment data but can't write SQL. InsightXpert bridges this gap through a chat interface that:

1. Translates natural language to SQL
2. Executes queries safely (read-only, with row limits and timeouts)
3. Returns layered answers with evidence, provenance, caveats, and follow-up suggestions
4. Auto-generates visualizations (bar, pie, line, grouped-bar charts)
5. Shows real-time agent reasoning in a process timeline

**Evaluation Criteria:**
| Criterion | Weight |
|-----------|--------|
| Insight Accuracy | 30% |
| Query Understanding | 25% |
| Explainability | 20% |
| Conversational Quality | 15% |
| Innovation & Technical Implementation | 10% |

---

## 3. How It Works (End-to-End)

Here's what happens when a user types "What is the average transaction amount by merchant category?":

### Step 1: Frontend sends message

The chat input captures the question. `useSSEChat()` hook opens an SSE (Server-Sent Events) connection to `POST /api/chat` with the message and conversation ID. Auth cookies are included automatically.

### Step 2: Backend authenticates and prepares

The route handler validates the JWT cookie, loads conversation history from both stores (in-memory for LLM context, persistent for full replay), saves the user message, and starts the analyst loop.

### Step 3: RAG retrieval

Before calling the LLM, the system searches ChromaDB for relevant context:
- **5 similar Q→SQL pairs** — past questions and their SQL (acts as few-shot examples)
- **3 DDL sections** — relevant table schemas
- **3 documentation chunks** — business context and column descriptions
- **2 anomaly findings** — previously detected patterns

This context is injected into the system prompt via Jinja2 templating.

### Step 4: System prompt assembly

A Jinja2 template (`analyst_system.j2`) is rendered with:
- Agent identity ("You are InsightXpert AI data analyst...")
- Full 17-column DDL for the `transactions` table
- Business documentation (what each column means, NULL handling, domain rules)
- 7 domain rules (SELECT only, fraud_flag semantics, ROUND(2), correlation != causation, etc.)
- 5-layer response structure requirement
- Visualization guidelines (when to use bar vs pie vs line vs grouped-bar vs table)
- RAG context (conditionally injected only when matches found)

### Step 5: LLM tool-calling loop (max 10 iterations)

The LLM (Gemini by default) receives the prompt, conversation history, and tool definitions. It reasons about the question and decides which tools to call:

**Iteration 1:** LLM decides to call `run_sql` with:
```sql
SELECT merchant_category, ROUND(AVG(amount_inr), 2) as avg_amount
FROM transactions
GROUP BY merchant_category
ORDER BY avg_amount DESC
```

The backend:
1. Streams a `tool_call` chunk → frontend shows "Calling run_sql" in the agent timeline
2. Streams a `sql` chunk → frontend renders syntax-highlighted SQL
3. Executes the query against SQLite (with row limit=1000, timeout=30s, read-only enforcement)
4. Streams a `tool_result` chunk → frontend renders data table + auto-detected bar chart
5. Appends the result to messages and loops back to the LLM

**Iteration 2:** LLM sees the results and generates a plain-language answer following the 5-layer structure.

The backend streams an `answer` chunk → frontend renders markdown.

### Step 6: Auto-learning

The successful Q→SQL pair is automatically saved to ChromaDB's `qa_pairs` collection, improving future retrieval for similar questions.

### Step 7: Conversation persistence

The assistant's answer is saved to:
- **In-memory store** — LRU cache (500 conversations, 2h TTL, last 20 turns) for fast LLM context
- **Persistent store** — SQLite with full message + chunks JSON for history replay

### Step 8: Frontend rendering

Throughout this process, the frontend receives chunks via SSE and renders them in real-time:
- `status` → Spinner with label ("Analyzing question...")
- `tool_call` → Pulsing indicator ("Calling run_sql")
- `sql` → Collapsible syntax-highlighted SQL block with copy button
- `tool_result` → Data table + auto-detected chart (bar/pie/line/grouped-bar)
- `answer` → Markdown-rendered response
- `error` → Red error card (if something fails)

The right sidebar shows the agent process timeline with expandable details for each step.

---

## 4. Backend Architecture

**Tech:** Python 3.11, FastAPI, SQLAlchemy, ChromaDB, Google Gemini, uv package manager

### 4.1 Entry Point (`main.py`)

FastAPI app with async lifespan management. On startup:
1. Loads settings from environment variables (Pydantic Settings)
2. Connects to SQLite database (single `insightxpert.db` for data + auth + conversations)
3. Initializes ChromaDB vector store
4. Creates LLM provider (Gemini, Ollama, or Vertex AI)
5. Creates auth database tables (users, conversations, messages, feedback, datasets, automations, insights, notifications, etc.) and seeds admin user
6. Runs database migrations for schema changes
7. Initializes both conversation stores
8. Computes and caches dataset statistics (`dataset_stats` table)
9. Bootstraps RAG with training data (DDL, docs, 12+ Q→SQL pairs)
10. Starts automation scheduler (APScheduler for cron-based automations)
11. Registers 6 routers: API, Auth, Admin, Client Config, Datasets, Insights

### 4.2 Agent System (`agents/`)

The system supports **3 analysis modes**, each with a different agent pipeline:

| Mode | Pipeline | Use Case |
|------|----------|----------|
| **Basic** | Single analyst → answer | Simple factual queries |
| **Agentic** | Orchestrator → DAG of analyst + quant tasks → enrichment evaluation → response synthesis → insight quality gate | Complex multi-faceted analysis |
| **Deep Think** | Agentic pipeline + dimension extraction (5W1H) → investigation evaluator → investigation synthesis | Exhaustive exploration of a topic |

**Key agent files:**
- `analyst.py` — Core SQL analyst loop (RAG → LLM → tool-calling → answer)
- `orchestrator_planner.py` — Plans and schedules parallel sub-tasks as a DAG
- `dag_executor.py` — Executes planned tasks in parallel (respecting dependencies)
- `quant_analyst.py` — Statistical analysis agent with Python-based tools
- `deep_think.py` — Dimension extraction and investigation pipeline
- `response_generator.py` — Synthesizes multi-task results into coherent response
- `clarifier.py` — Detects ambiguous queries and asks clarifying questions
- `common.py` — Shared types (`ChatChunk`, `ToolCallRecord`, `AgentContext`)

All agent loops are `async def` generators yielding `ChatChunk` objects. Error handling wraps all LLM calls — failures yield error chunks instead of crashing the stream. Each loop enforces a max iteration limit (default 10).

### 4.3 Tools (`agents/tool_base.py`, `agents/tools.py`, `agents/stat_tools.py`, `agents/advanced_tools.py`)

**Abstract Base Class pattern:**
- `Tool` ABC: `name`, `description`, `get_args_schema()`, `execute()`
- `ToolRegistry`: manages tools, generates JSON schemas for the LLM, executes with error handling
- Error sanitization: tool errors return clean messages, never stack traces

**21 tools across 3 registries:**

**Core tools** (analyst — `tools.py`):
| Tool | Purpose |
|------|---------|
| `RunSqlTool` | Execute SELECT queries (row limit, timeout, read-only) |
| `GetSchemaTool` | Inspect table DDL |
| `SearchSimilarTool` | Query ChromaDB knowledge base |
| `ClarifyTool` | Ask the user a clarifying question (when `clarification_enabled`) |

**Statistical tools** (quant analyst — `stat_tools.py`):
| Tool | Purpose |
|------|---------|
| `RunSqlTool` | Execute queries for statistical analysis |
| `DescriptiveStatsTool` | count, mean, std, quartiles, skewness, kurtosis |
| `HypothesisTestTool` | chi-squared, t-test, Mann-Whitney, ANOVA, z-proportion |
| `CorrelationTool` | Pearson, Spearman, Kendall with p-values |
| `FitDistributionTool` | normal, exponential, lognormal, gamma, Weibull ranking by KS-test |
| `RunPythonTool` | Execute Python code for custom analysis |

**Advanced tools** (agentic/deep mode — `advanced_tools.py`):
14 specialized tools including time-series analysis, fraud/risk analytics, trend detection, anomaly scoring, cohort analysis, funnel analysis, and general analytics tools.

### 4.4 LLM Providers (`llm/`)

**Protocol-based design:**
```
LLMProvider protocol:
  .model → str
  .chat(messages, tools) → LLMResponse
  .chat_stream(messages, tools) → AsyncGenerator[LLMChunk]
```

**Factory pattern:** `create_llm("gemini", settings)` uses a registry of factory functions. No if/else chains. Adding a new provider = write the class + register a factory.

**Three providers:**
- **Gemini** (`gemini.py`) — Uses `google-genai` async client. Handles function calling, streaming, multipart content. Primary production provider.
- **Ollama** (`ollama.py`) — Uses `ollama` async client with 120s timeout. Same protocol, local development fallback.
- **Vertex AI** (`vertex.py`) — Google Cloud Vertex AI for enterprise deployments.

**Runtime switching:** `POST /api/config/switch` hot-swaps the LLM without restart. Validates model exists first (rolls back on failure).

### 4.5 Database (`db/`)

**Connector** (`connector.py`): SQLAlchemy wrapper with:
- Connection pooling with pre-ping
- Row limit enforcement (default 1000)
- Query timeout (default 30s)
- Dual read-only protection:
  1. Regex blocklist: catches INSERT/UPDATE/DELETE/DROP/ALTER/CREATE
  2. Engine-level: `PRAGMA query_only = ON` (blocks writes at SQLite level)

**Schema introspection** (`schema.py`): DDL generation for all tables.

### 4.6 Prompts (`prompts/`)

15 Jinja2 templates rendered per query, organized by agent role:

| Template | Purpose |
|----------|---------|
| `analyst_system.j2` | Main SQL analyst (identity, DDL, docs, rules, RAG, viz guidelines) |
| `statistician_system.j2` | Statistical analysis (hypothesis testing, effect sizes, CIs) |
| `quant_analyst_system.j2` | Quantitative analyst for agentic mode |
| `orchestrator_planner.j2` | Plans multi-task DAGs from user questions |
| `enrichment_evaluator.j2` | Evaluates if analyst results need enrichment |
| `investigation_evaluator.j2` | Deep think: evaluates investigation completeness |
| `dimension_extractor.j2` | Deep think: extracts 5W1H dimensions from questions |
| `response_synthesizer.j2` | Combines multi-task results into final response |
| `insight_quality_gate.j2` | Quality-checks generated insights before saving |
| `investigation_synthesizer.j2` | Synthesizes investigation findings |
| `clarifier_system.j2` | Ambiguity detection and clarification prompts |
| `nl_trigger.j2` | Natural-language trigger evaluation for automations |
| `automation_namer.j2` | Auto-names automations from SQL queries |
| `sql_generator.j2` | NL→SQL generation for automation workflows |
| `title_generator.j2` | Auto-generates conversation titles |

Conditional sections inject RAG context only when matches are found:
```jinja2
{% if similar_qa %}
## Similar Past Queries
{% for item in similar_qa %}{{ item.document }}{% endfor %}
{% endif %}
```

### 4.7 Admin System (`admin/`)

Multi-tenant configuration system:
- **Feature toggles:** 9 switches — SQL executor, model switching, RAG training, RAG retrieval, chart rendering, conversation export, agent process sidebar, clarification enabled, stats context injection
- **Org branding:** Custom display name, logo URL, CSS theme variable overrides, color mode (dark/light)
- **User-org mappings:** Email → organization assignment
- **Admin domains:** Email domains that grant admin access

Stored as JSON on disk (`config/client-configs.json`). Admin endpoints require admin user.

### 4.8 Automations (`automations/`)

Scheduled data monitoring with trigger-based alerting:
- **Scheduler** (`scheduler.py`) — APScheduler runs cron-based automations
- **Evaluator** (`evaluator.py`) — Executes SQL workflows, evaluates trigger conditions (threshold, change detection, row count, column expression, slope)
- **NL Trigger** (`nl_trigger.py`) — Natural-language trigger evaluation via LLM
- Multi-step SQL workflows with topological execution order
- Notifications dispatched when triggers fire (with severity levels)

### 4.9 Insights (`insights/`)

Auto-generated insights from the enrichment pipeline:
- Insights created during agentic/deep analysis and quality-gated before saving
- CRUD API for viewing, bookmarking, and managing insights
- Categories derived from enrichment tasks (temporal, segmentation, risk, etc.)

### 4.10 Datasets (`datasets/`)

Multi-dataset support:
- **Dataset service** (`service.py`) — CRUD for user-uploaded datasets
- **Data loader** (`db/data_loader.py`) — CSV → SQLite loader with schema inference
- **Stats computer** (`db/stats_computer.py`) — Pre-computes summary statistics for stats context injection

---

## 5. Frontend Architecture

**Tech:** Next.js 16 (App Router), React 19, TypeScript, Zustand, Tailwind CSS 4, shadcn/ui, Recharts, Framer Motion

### 5.1 Pages

| Route | Component | Auth |
|-------|-----------|------|
| `/` | Chat interface (AppShell + ChatPanel) | Required (AuthGuard) |
| `/login` | Email/password form | Public |
| `/register` | User registration form | Public |
| `/admin` | Admin dashboard (config, users, conversations) | Admin only |
| `/admin/automations` | Automation management | Admin only |
| `/admin/notifications` | Notification management | Admin only |

### 5.2 Layout (3-Column)

```
┌─────────────────────────────────────────────────────┐
│                      Header                          │
│  [Logo]  [Model Selector]  [SQL]  [Theme]  [User]   │
├──────────┬──────────────────────┬───────────────────┤
│  Left    │                      │  Right             │
│  Sidebar │    Chat Panel        │  Sidebar           │
│          │                      │                    │
│  Conv    │  Messages            │  Agent Process     │
│  History │  + Input             │  Steps Timeline    │
│  Search  │  + Welcome Screen    │  + Details         │
│          │  + Charts/Tables     │                    │
├──────────┴──────────────────────┴───────────────────┤
└─────────────────────────────────────────────────────┘
```

- **Sidebars:** Collapsible on desktop (Framer Motion), Sheet overlays on mobile
- **Responsive:** Tailwind breakpoints + `useMediaQuery` hook + safe area padding

### 5.3 State Management (7 Zustand Stores)

| Store | State | Key Actions |
|-------|-------|-------------|
| **auth-store** | `user`, `isLoading`, `error` | `login()`, `register()`, `logout()`, `checkAuth()` |
| **chat-store** | `conversations[]`, `activeConversationId`, `isStreaming`, `agentSteps[]`, sidebar states, clarification state, agent phase | `newConversation()`, `addUserMessage()`, `appendChunk()`, `finishStreaming()`, `loadConversationMessages()` |
| **settings-store** | `currentProvider`, `currentModel`, `providers[]`, `agentMode` | `fetchConfig()`, `switchModel()`, `setAgentMode()` |
| **client-config-store** | `config` (org settings), `isAdmin`, `orgId` | `fetchConfig()` (applies branding CSS vars, sets document title) |
| **insight-store** | `insights[]`, `allInsights[]`, `totalCount` | `fetchInsights()`, `bookmarkInsight()`, `deleteInsight()`, `fetchCount()` |
| **automation-store** | `automations[]`, workflow builder state, test triggers | CRUD, workflow builder (blocks, edges, topological sort), trigger testing, SQL generation |
| **notification-store** | `notifications[]`, `unreadCount` | `fetchNotifications()`, `markAsRead()`, `markAllAsRead()`, `fetchUnreadCount()` |

### 5.4 SSE Streaming (`hooks/use-sse-chat.ts`)

The core streaming hook orchestrates:
1. Creates/reuses conversation
2. Opens SSE connection with POST body (not GET — supports request body)
3. Parses newline-delimited JSON chunks with microtask batching (React 18+ auto-batches state updates)
4. Updates Zustand stores in real-time
5. Manages agent step timeline (pending → running → done/error)
6. Handles AbortController for stop functionality
7. Tracks wall-clock time from send to `[DONE]`
8. Refreshes insight badge count on insight chunks

### 5.5 Chunk Rendering (`components/chunks/`)

Each SSE chunk type has a dedicated React component:

| Chunk | Component | What It Renders |
|-------|-----------|-----------------|
| `status` | StatusChunk | Spinner + label (e.g., "Searching knowledge base...") |
| `tool_call` | ToolCallChunk | Pulsing dot + tool name |
| `sql` | SqlChunk | Collapsible SQL with syntax highlighting (vs2015 theme) + copy button |
| `tool_result` | ToolResultChunk | Collapsible data table + auto-detected chart |
| `answer` | AnswerChunk | GitHub-flavored Markdown via react-markdown (React.memo optimized) |
| `error` | ErrorChunk | Red error card with description |
| `clarification` | ClarificationChunk | Clarification request when query is ambiguous |
| `stats_context` | StatsContextChunk | Dataset statistics injection display |
| `insight` | InsightChunk | Auto-generated insight with enrichment metadata |
| `enrichment_trace` | ThinkingTrace | Enrichment task trace (collapsible) |
| `orchestrator_plan` | ThinkingTrace | DAG plan with task breakdown |
| `agent_trace` | ThinkingTrace | Individual agent execution trace |
| `metrics` | (internal) | Token counts and generation time |

### 5.6 Chart Auto-Detection (`lib/chart-detector.ts`)

Heuristic-based chart type selection from query results:
- **Pie:** 2-10 rows, 1 category + 1 numeric column (parts of a whole)
- **Grouped Bar:** 2 category columns + 1+ numeric (cross-tabulations)
- **Line:** Temporal column detected by name (date, month, year, quarter, etc.)
- **Bar:** 1+ category + 1+ numeric, default for most aggregations
- **Table:** Fallback for single-row results, wide tables, or no clear chart fit

Also auto-abbreviates Indian state names to 2-letter RTO codes (Maharashtra → MH) for chart readability.

### 5.7 Key UI Features

- **Welcome Screen:** Logo, subtitle, centered input, animated suggested questions
- **Sample Questions Modal:** Categorized example questions to help users get started
- **Message Actions:** Copy prompt/response, thumbs up/down feedback with optional comment, retry last message
- **Model Selector:** Breadcrumb-style `Provider / Model` dropdowns in header with runtime switching
- **Agent Mode Toggle:** Switch between basic, agentic, and deep think modes from the input toolbar
- **SQL Executor:** Right-side sheet panel with read-only SQL editor, Ctrl/Cmd+Enter execution, results table with chart configurator
- **Conversation Management:** Create, rename, delete, search conversations in left sidebar
- **Theme Toggle:** Dark/light mode with localStorage persistence
- **Agent Timeline:** Real-time process steps with expandable details (LLM reasoning, SQL, results, RAG context)
- **Insight Bell:** Badge with unread count, popover preview, full gallery modal with bookmark/delete
- **Notification Bell:** Automation alerts with severity levels, mark-as-read, detail modals
- **Dataset Viewer:** Schema browser and sample data explorer
- **Dataset Selector:** Switch between uploaded datasets
- **Workflow Builder:** Visual DAG editor using React Flow — drag SQL blocks, connect edges, auto-suggest edges by shared tables, topological sort for execution order
- **Automation Management:** Create, edit, toggle, delete automations with cron scheduling, trigger conditions, run history
- **Report Export:** Export conversation results to PDF/CSV
- **Trace Modal:** Detailed inspection of agent reasoning traces
- **Health Check Gate:** Backend health verification on app startup

### 5.8 Styling

- **Tailwind CSS 4** with OKLch color space
- **Custom utilities:** `.glass` (glassmorphism, backdrop-blur), `.glass-input` (elevated glow for chat input)
- **Fonts:** Inter (body), JetBrains Mono (code/data)
- **Components:** shadcn/ui New York style with Radix UI accessible primitives
- **Dark mode by default:** Custom scrollbar styling, smooth transitions

---

## 6. Database & Data

### 6.1 Transaction Database

**File:** `insightxpert.db` (~80MB SQLite)
**Rows:** 250,000 synthetic Indian digital payment transactions
**Generator:** `generate_data.py` (deterministic seed=42)

**Schema (17 columns):**

| Column | Type | Example Values |
|--------|------|----------------|
| `transaction_id` | TEXT PK | TXN0000000001 |
| `timestamp` | TEXT | 2024-10-08 15:17:28 |
| `transaction_type` | TEXT | P2P, P2M, Bill Payment, Recharge |
| `merchant_category` | TEXT | Food, Grocery, Fuel, Entertainment, Shopping, Healthcare, Education, Transport, Utilities, Other |
| `amount_inr` | REAL | 50.00 - 9999.00 |
| `transaction_status` | TEXT | SUCCESS, FAILED |
| `sender_age_group` | TEXT | 18-25, 26-35, 36-45, 46-55, 56+ |
| `receiver_age_group` | TEXT | (same as above) |
| `sender_state` | TEXT | Maharashtra, Uttar Pradesh, Karnataka, Tamil Nadu, Gujarat, Rajasthan, West Bengal, Telangana, Delhi, Andhra Pradesh |
| `sender_bank` | TEXT | SBI, HDFC, ICICI, Axis, PNB, Kotak, IndusInd, Yes Bank |
| `receiver_bank` | TEXT | (same as above) |
| `device_type` | TEXT | Android, iOS, Web |
| `network_type` | TEXT | 4G, 5G, WiFi, 3G |
| `fraud_flag` | INTEGER | 0 (not flagged), 1 (flagged for review) |
| `hour_of_day` | INTEGER | 0-23 |
| `day_of_week` | TEXT | Monday - Sunday |
| `is_weekend` | INTEGER | 0 or 1 |

**8 indices** for query performance: transaction_type, status, merchant_category, sender_bank, device_type, fraud_flag, hour_of_day, is_weekend, sender_state.

### 6.2 Auth & Application Tables

All application tables live in the same `insightxpert.db` file as the transactions data.

**Core tables (22 total):**
- `users` — id (UUID), email (unique), hashed_password, is_active, is_admin, org_id, created_at, last_active
- `conversations` — id, user_id (FK), title, is_starred, created_at, updated_at
- `messages` — id, conversation_id (FK), role, content, chunks_json, feedback, feedback_comment, input_tokens, output_tokens, generation_time_ms, created_at
- `feedback` — id, user_id (FK), conversation_id, message_id, rating, comment, created_at
- `automations` — id, user_id, name, description, nl_query, sql_query, sql_queries (JSON), cron_expression, trigger_conditions (JSON), is_active, workflow_graph (JSON), etc.
- `automation_runs` — id, automation_id (FK), status, result_json, triggers_fired, error_message, etc.
- `insights` — id, user_id, org_id, conversation_id, message_id, title, summary, content, categories (JSON), is_bookmarked, source, etc.
- `notifications` — id, user_id, automation_id, run_id, title, message, severity, is_read, etc.
- `datasets` — id, user_id, name, file_path, table_name, row_count, schema_json, etc.
- `dataset_stats` — pre-computed summary statistics per dataset dimension
- `trigger_templates` — reusable trigger condition templates
- `_sync_deletes` — delete tracking for Turso background sync (when enabled)

**Default admin:** `admin@insightxpert.ai` / `admin123` (auto-seeded on startup)

### 6.3 Supported Query Types

| Category | Example Question |
|----------|-----------------|
| **Descriptive** | "What is the average transaction amount for bill payments?" |
| **Comparative** | "How do failure rates compare between Android and iOS users?" |
| **Temporal** | "What are the peak transaction hours for food delivery?" |
| **Segmentation** | "Which age group uses P2P transfers most frequently?" |
| **Correlation** | "Is there a relationship between network type and transaction success?" |
| **Risk Analysis** | "What percentage of high-value transactions are flagged for review?" |

---

## 7. RAG & Memory Systems

### 7.1 ChromaDB Vector Store

4 collections with semantic search and auto-deduplication (SHA256 IDs):

| Collection | Content | Search Method | Default N |
|-----------|---------|---------------|-----------|
| `qa_pairs` | Question→SQL pairs (hand-crafted + auto-learned) | `search_qa()` | 5 |
| `ddl` | Table schemas | `search_ddl()` | 3 |
| `docs` | Business documentation | `search_docs()` | 3 |
| `findings` | Anomaly findings | `search_findings()` | 3 |

**Auto-learning:** Every successful Q→SQL pair is saved, improving future retrieval.

**Training bootstrap:** On startup, the trainer loads:
- DDL constant (17-column transactions table)
- Business documentation (column descriptions, NULL semantics, domain rules)
- 12+ example Q→SQL pairs across 6 categories

### 7.2 Dual-Store Conversation Memory

| Store | Purpose | Capacity | Storage |
|-------|---------|----------|---------|
| **In-memory** (LRU) | Fast LLM context | 500 conversations, 2h TTL, last 20 turns | RAM |
| **Persistent** (SQLite) | Full history replay | Unlimited | `insightxpert.db` |

The in-memory store holds condensed messages (user questions + assistant answers only, no tool intermediaries) for injecting into LLM context. The persistent store holds everything including full chunks JSON for UI replay.

`get_or_create_conversation()` bridges frontend-generated IDs with backend storage — it looks up by ID and creates if not found, solving the ID mismatch between client and server.

---

## 8. Authentication & Admin

### 8.1 Auth Flow

```
Login:
  POST /api/auth/login {email, password}
    → bcrypt.verify(password, hashed_password)
    → create JWT (HS256, 24h expiry)
    → Set HttpOnly cookie "access_token"
    → Return {id, email, is_admin}

Protected route:
  Request with cookie
    → get_current_user() dependency
    → Extract + decode JWT from cookie
    → Fetch User from SQLite
    → Inject user into route handler
```

### 8.2 Admin System

Multi-tenant configuration via JSON file on disk:

- **Feature Toggles:** 9 boolean flags control which features are visible per organization
  - sql_executor, model_switching, rag_training, rag_retrieval, chart_rendering, conversation_export, agent_process_sidebar, clarification_enabled, stats_context_injection
- **Org Branding:** Custom display name, logo URL, CSS theme color overrides, color mode
- **User-Org Mappings:** Map email addresses to organizations
- **Admin Domains:** Email domains that automatically grant admin access

Admin endpoints (`/api/admin/*`) require admin user. Public endpoint (`/api/client-config`) returns resolved config for the current user based on their org mapping.

Frontend admin pages at `/admin`, `/admin/automations`, and `/admin/notifications` provide UI for all configuration with guards that redirect non-admins.

---

## 9. API Reference

### Chat & Streaming

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/chat` | Yes | SSE streaming text-to-SQL (primary endpoint) |
| POST | `/api/chat/poll` | Yes | Blocking text-to-SQL (returns all chunks at once) |

### Configuration

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/config` | Yes | List LLM providers & available models |
| POST | `/api/config/switch` | Yes | Hot-swap LLM provider/model at runtime |
| GET | `/api/client-config` | Yes | Get resolved org config (features, branding) |

### Database

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/schema` | Yes | Introspect database schema |
| POST | `/api/sql/execute` | No | Execute read-only SQL directly |

### Conversations

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/conversations` | Yes | List all conversations for user |
| GET | `/api/conversations/{id}` | Yes | Get conversation with full messages |
| PATCH | `/api/conversations/{id}` | Yes | Rename conversation |
| DELETE | `/api/conversations/{id}` | Yes | Delete conversation |
| GET | `/api/conversations/search?q=` | Yes | Full-text search conversations |

### Auth

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/login` | No | Email + password → JWT cookie |
| POST | `/api/auth/logout` | No | Clear auth cookie |
| GET | `/api/auth/me` | Yes | Get current user |

### Training & Feedback

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/train` | Yes | Add Q→SQL pair, DDL, or documentation to RAG |
| GET | `/api/rag/delete` | Yes | Clear all RAG embeddings |
| POST | `/api/feedback` | Yes | Submit message feedback (thumbs up/down + comment) |

### Automations

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/automations` | Yes | List automations |
| POST | `/api/automations` | Yes | Create automation |
| PUT | `/api/automations/{id}` | Yes | Update automation |
| DELETE | `/api/automations/{id}` | Yes | Delete automation |
| PATCH | `/api/automations/{id}/toggle` | Yes | Toggle automation active/inactive |
| POST | `/api/automations/{id}/run` | Yes | Run automation now |
| GET | `/api/automations/{id}/runs` | Yes | Get run history |
| POST | `/api/automations/generate-sql` | Yes | NL → SQL generation for workflows |

### Insights

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/insights` | Yes | List insights (with optional `?bookmarked=true`) |
| GET | `/api/insights/all` | Yes | All insights (for gallery) |
| GET | `/api/insights/count` | Yes | Badge count |
| PATCH | `/api/insights/{id}/bookmark` | Yes | Toggle bookmark |
| DELETE | `/api/insights/{id}` | Yes | Delete insight |

### Notifications

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/notifications` | Yes | List notifications |
| GET | `/api/notifications/all` | Yes | All notifications |
| GET | `/api/notifications/count` | Yes | Unread count |
| PATCH | `/api/notifications/{id}/read` | Yes | Mark as read |
| POST | `/api/notifications/mark-all-read` | Yes | Mark all as read |

### Datasets

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/datasets` | Yes | List datasets |
| POST | `/api/datasets` | Yes | Upload dataset |
| GET | `/api/datasets/{id}` | Yes | Get dataset details |
| DELETE | `/api/datasets/{id}` | Yes | Delete dataset |
| GET | `/api/datasets/{id}/schema` | Yes | Get dataset schema |
| GET | `/api/datasets/{id}/sample` | Yes | Get sample rows |

### Admin

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/admin/config` | Admin | Get full admin config |
| PUT | `/api/admin/config` | Admin | Update global config |
| GET | `/api/admin/organizations` | Admin | List organizations |
| GET/PUT/DELETE | `/api/admin/config/{org_id}` | Admin | CRUD organization config |

### Health

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/health` | No | Health check |

---

## 10. Deployment & Infrastructure

### 10.1 Architecture

```
GitHub push to main
        │
        ├── deploy-backend (Job 1)
        │     ├── Authenticate via Workload Identity Federation
        │     ├── Docker build (backend/)
        │     ├── Push image to GCR
        │     └── Deploy to Cloud Run
        │
        └── deploy-frontend (Job 2, after backend)
              ├── Build Next.js static export
              └── Deploy to Firebase Hosting
```

### 10.2 Production Infrastructure

| Component | Service | Details |
|-----------|---------|---------|
| **Backend** | Cloud Run | 1 CPU, 1Gi RAM, min 1 / max 3 instances, 300s timeout |
| **Frontend** | Firebase Hosting | Static export, 1-year cache for assets |
| **Container Registry** | GCR | Docker images tagged by commit SHA |
| **Auth** | Workload Identity Federation | Keyless — no service account JSON keys |
| **Domain** | Firebase | insightxpert-ai.web.app |

Firebase Hosting rewrites `/api/**` to Cloud Run, so the frontend uses relative API paths.

### 10.3 Docker Build

```dockerfile
FROM python:3.11-slim
# Install uv (fast Python package manager)
# Install dependencies from pyproject.toml + uv.lock
# Copy source code
# Generate 250K transactions at build time (DB is baked into image)
# Pre-download ChromaDB ONNX model
# Expose port 8080, run uvicorn
```

### 10.4 CI/CD

**Production** (`deploy.yml`): Push to main → build + deploy backend → build + deploy frontend

**PR Preview** (`preview.yml`): PR to main → run pytest + lint + build → deploy preview channel → post URL as PR comment

### 10.5 GCP Resources

| Resource | Value |
|----------|-------|
| Project ID | `insightx-487005` |
| Cloud Run service | `insightxpert-api` (us-central1) |
| Firebase site | `insightxpert-ai` |
| WIF service account | `github-actions@insightx-487005.iam.gserviceaccount.com` |

### 10.6 Secrets

| Secret | Purpose |
|--------|---------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `SECRET_KEY` | JWT signing key |

---

## 11. Design Patterns & Decisions

### 11.1 From-Scratch Engine (not Vanna)

Vanna was replaced with a custom ~600-line engine for:
1. **Custom agent loop** — multi-step tool-calling reasoning, not single-shot SQL
2. **Full explainability control** — layered responses with provenance and caveats
3. **Custom SSE streaming** — typed chunks with real-time progress
4. **Extension points** — easy to add agents, tools, providers without touching core code

### 11.2 Protocol-Based Abstraction

Both `LLMProvider` and `VectorStoreBackend` use Python protocols (`@runtime_checkable`). This decouples all consumers from concrete implementations. Tests use `InMemoryVectorStore` (difflib-based) with zero external dependencies. Protocol conformance is verified at import time via `issubclass` assertions.

### 11.3 Factory Pattern (LLM)

`create_llm(provider, settings)` uses a registry of factory functions (lazy imports). Adding a new provider = write the class + register one function. No if/else chains anywhere.

### 11.4 Tool ABC + Registry

Each tool is a class with `name`, `description`, `get_args_schema()`, `execute()`. The registry manages dispatch, schema generation, and error sanitization (no stack traces leaked to LLM or user).

### 11.5 Jinja2 Prompt Templates

System prompts are Jinja2 templates with conditional RAG context injection. This separates prompt content from Python code and supports per-query dynamic context.

### 11.6 Dual-Store Conversation Memory

In-memory LRU (fast, ephemeral, for LLM context) + SQLite persistent (durable, for history replay). `get_or_create_conversation()` bridges frontend-generated and backend-stored IDs.

### 11.7 Guardrails

- **No causal claims** — only correlation language allowed
- **fraud_flag semantics** — always "flagged for review", never "confirmed fraud"
- **Dual SQL protection** — regex blocklist + SQLite `PRAGMA query_only`
- **Row limits** — 1000 rows max per query
- **Timeouts** — 30s per query
- **Error sanitization** — no stack traces leaked to LLM or user
- **LLM switch validation** — validates model exists before mutating, rolls back on failure

---

## 12. Testing

### 12.1 Backend (`backend/tests/`)

| File | Tests |
|------|-------|
| `test_agent.py` | Agent loop execution, tool calling, RAG training |
| `test_db.py` | Database connector, queries, schema introspection, error handling |
| `test_rag.py` | All 4 collections, search, deduplication, distance metrics |
| `test_statistician.py` | Statistical analysis tools |
| `conftest.py` | Fixtures: in-memory SQLite, temporary ChromaDB, test settings |

Run: `cd backend && uv run pytest`

### 12.2 Frontend

- **Linting:** ESLint 9 with Next.js config
- **E2E:** Playwright (configured but minimal tests)
- **Type checking:** TypeScript strict mode

Run: `cd frontend && npm run lint`

---

## 13. What's Implemented vs Planned

### Implemented (Production-Ready)

**Agent Pipeline:**
- 3 analysis modes: basic (single analyst), agentic (multi-agent DAG), deep think (exhaustive investigation)
- Orchestrator planner with DAG-based task decomposition and parallel execution
- SQL analyst agent with full tool-calling loop and error recovery
- Quant analyst agent with statistical Python tools
- Enrichment evaluator — decides if analyst results need additional analysis
- Response synthesizer — combines multi-task results into coherent response
- Insight quality gate — validates generated insights before saving
- Deep think pipeline: dimension extraction (5W1H) → investigation evaluator → investigation synthesis
- Ambiguity detection with clarification requests (clarifier agent)
- 21 tools across 3 registries (core, statistical, advanced)

**LLM & RAG:**
- 3 LLM providers: Gemini, Ollama, Vertex AI with runtime switching
- ChromaDB vector store with 4 collections and auto-learning
- Pre-computed dataset statistics with context injection

**Backend Infrastructure:**
- Database connector with dual read-only enforcement
- JWT + bcrypt authentication with persistent conversations
- Admin system with 9 feature toggles, org branding, user-org mappings
- Automation scheduler with cron-based execution, trigger conditions, and notifications
- Auto-generated insights with bookmark/delete management
- Multi-dataset support with upload, schema inference, and stats computation
- 50+ API endpoints across 6 routers
- 15 Jinja2 prompt templates
- CI/CD with GitHub Actions, Cloud Run, Firebase Hosting

**Frontend:**
- Full chat UI with SSE streaming, 13+ chunk types, agent timeline
- 3-column responsive layout with dark/light theme
- 7 Zustand stores (auth, chat, settings, client-config, insight, automation, notification)
- Workflow builder with React Flow visual DAG editor
- Insight bell with gallery modal and bookmarking
- Notification bell with severity levels and detail modals
- Dataset viewer and selector
- SQL executor with chart configurator
- Sample questions modal
- Report export (PDF/CSV)
- Health check gate on startup

### Not Implemented

- Observability dashboard (tracer + store stubs exist but are unused)
- Starred conversations UI (backend column exists, no frontend toggle)

---

## 14. File Map

```
InsightXpert/
├── README.md                       # Project overview & setup guide
├── ARCHITECTURE.md                 # Original technical blueprint (Feb 17)
├── DEPLOY.md                       # Deployment guide
├── WALKTHROUGH.md                  # This file
├── CLAUDE.md                       # AI assistant instructions
├── TODO.md                         # Remaining work items
├── DESIGN_PATTERNS.md              # Design patterns reference
├── firebase.json                   # Firebase Hosting config
├── .env.example                    # Environment variable template
│
├── docs/                           # Comprehensive documentation
│   ├── architecture.md             # System architecture
│   ├── agent-pipeline.md           # Agent pipeline deep dive
│   ├── agent-tools.md              # All 21 tools reference
│   ├── AGENTS_AND_MODES.md         # Agent modes & orchestration
│   ├── api-reference.md            # Full API reference
│   ├── automations.md              # Automations system
│   ├── configuration.md            # Configuration reference
│   ├── contributing.md             # Contributing guide
│   ├── dataset.md                  # Dataset documentation
│   ├── frontend.md                 # Frontend architecture
│   └── top-10-analyses.md          # Example analysis showcase
│
├── .github/workflows/
│   ├── deploy.yml                  # Production CI/CD
│   └── preview.yml                 # PR preview CI/CD
│
├── prd/QuestionBank/               # Problem statement & evaluation criteria
│
├── postman/                        # API collection for testing
│
├── backend/
│   ├── pyproject.toml              # Python deps (hatchling, Python 3.11+)
│   ├── uv.lock                     # Locked dependency versions
│   ├── Dockerfile                  # Cloud Run container
│   ├── generate_data.py            # 250K transaction data generator
│   ├── insightxpert.db             # SQLite DB (data + auth + conversations)
│   ├── chroma_data/                # ChromaDB persistent vector store
│   ├── config/client-configs.json  # Admin configuration
│   │
│   ├── tests/
│   │   ├── conftest.py             # Test fixtures
│   │   ├── test_agent.py           # Agent loop tests
│   │   ├── test_api_chat.py        # Chat API integration tests
│   │   ├── test_db.py              # Database tests
│   │   ├── test_rag.py             # RAG tests
│   │   └── test_statistician.py    # Stats tools tests
│   │
│   └── src/insightxpert/
│       ├── main.py                 # FastAPI app entry point + lifespan
│       ├── config.py               # Pydantic Settings
│       ├── exceptions.py           # Custom exception classes
│       │
│       ├── api/
│       │   ├── routes.py           # Chat, config, SQL, conversation, feedback endpoints
│       │   └── models.py           # Request/response Pydantic models
│       │
│       ├── agents/
│       │   ├── analyst.py          # SQL analyst agent loop
│       │   ├── orchestrator_planner.py  # DAG task planner
│       │   ├── dag_executor.py     # Parallel task executor
│       │   ├── quant_analyst.py    # Statistical analysis agent
│       │   ├── deep_think.py       # Dimension extraction + investigation pipeline
│       │   ├── response_generator.py  # Multi-task response synthesizer
│       │   ├── clarifier.py        # Ambiguity detection + clarification
│       │   ├── common.py           # Shared types (ChatChunk, AgentContext)
│       │   ├── tool_base.py        # Tool ABC + ToolRegistry
│       │   ├── tools.py            # Core tools (RunSql, GetSchema, SearchSimilar, Clarify)
│       │   ├── stat_tools.py       # Statistical tools (6 tools)
│       │   ├── advanced_tools.py   # Advanced analytics tools (14 tools)
│       │   └── stats_resolver.py   # Stats context resolution
│       │
│       ├── prompts/                # 15 Jinja2 templates
│       │   ├── __init__.py         # Template loader
│       │   ├── analyst_system.j2
│       │   ├── statistician_system.j2
│       │   ├── quant_analyst_system.j2
│       │   ├── orchestrator_planner.j2
│       │   ├── enrichment_evaluator.j2
│       │   ├── investigation_evaluator.j2
│       │   ├── dimension_extractor.j2
│       │   ├── response_synthesizer.j2
│       │   ├── insight_quality_gate.j2
│       │   ├── investigation_synthesizer.j2
│       │   ├── clarifier_system.j2
│       │   ├── nl_trigger.j2
│       │   ├── automation_namer.j2
│       │   ├── sql_generator.j2
│       │   └── title_generator.j2
│       │
│       ├── llm/
│       │   ├── base.py             # LLMProvider protocol
│       │   ├── factory.py          # Registry-based factory
│       │   ├── gemini.py           # Google Gemini provider
│       │   ├── ollama.py           # Ollama local provider
│       │   └── vertex.py           # Google Vertex AI provider
│       │
│       ├── db/
│       │   ├── connector.py        # SQLAlchemy wrapper
│       │   ├── schema.py           # DDL introspection
│       │   ├── data_loader.py      # CSV → SQLite loader
│       │   ├── stats_computer.py   # Pre-computed dataset statistics
│       │   └── migrations.py       # Schema migrations
│       │
│       ├── rag/
│       │   ├── base.py             # VectorStoreBackend protocol
│       │   ├── store.py            # ChromaVectorStore (4 collections)
│       │   └── memory.py           # InMemoryVectorStore (testing)
│       │
│       ├── memory/
│       │   └── conversation_store.py   # In-memory LRU + TTL
│       │
│       ├── auth/
│       │   ├── routes.py           # Login, logout, register, me
│       │   ├── models.py           # 20+ ORM models (User, Conversation, Message, etc.)
│       │   ├── security.py         # JWT + bcrypt
│       │   ├── dependencies.py     # get_current_user
│       │   ├── conversation_store.py   # Persistent CRUD
│       │   ├── permissions.py      # Org-scoped permission checks
│       │   └── seed.py             # Admin user bootstrap
│       │
│       ├── admin/
│       │   ├── routes.py           # Admin endpoints
│       │   ├── config_store.py     # JSON config file management
│       │   └── models.py           # FeatureToggles, OrgConfig, etc.
│       │
│       ├── automations/
│       │   ├── routes.py           # Automation CRUD + run endpoints
│       │   ├── scheduler.py        # APScheduler cron-based execution
│       │   ├── evaluator.py        # SQL workflow executor + trigger evaluator
│       │   └── nl_trigger.py       # Natural-language trigger evaluation
│       │
│       ├── datasets/
│       │   ├── routes.py           # Dataset CRUD endpoints
│       │   └── service.py          # Dataset management service
│       │
│       ├── insights/
│       │   └── routes.py           # Insight CRUD + bookmark endpoints
│       │
│       ├── training/
│       │   ├── trainer.py          # RAG bootstrap
│       │   ├── schema.py           # DDL constant
│       │   ├── documentation.py    # Business context
│       │   └── queries.py          # 12+ example Q→SQL pairs
│       │
│       └── benchmark/              # Performance benchmarking
│           └── ...
│
└── frontend/
    ├── package.json                # Next.js 16, React 19, deps
    ├── next.config.ts              # API proxy, static export toggle
    ├── tsconfig.json               # TypeScript config
    ├── components.json             # shadcn/ui config
    ├── playwright.config.ts        # E2E testing
    │
    └── src/
        ├── app/
        │   ├── layout.tsx          # Root layout (fonts, metadata, health gate)
        │   ├── globals.css         # Tailwind 4 + OKLch + glassmorphism
        │   ├── page.tsx            # Home (AuthGuard + AppShell + ChatPanel)
        │   ├── login/page.tsx      # Login form
        │   ├── register/page.tsx   # Registration form
        │   └── admin/
        │       ├── layout.tsx      # Admin layout with guards
        │       ├── page.tsx        # Admin dashboard
        │       ├── automations/    # Automation management page
        │       └── notifications/  # Notification management page
        │
        ├── components/
        │   ├── auth/               # AuthGuard
        │   ├── health/             # HealthCheckGate
        │   ├── chat/               # ChatPanel, MessageList, MessageBubble,
        │   │                       # MessageInput, MessageActions, WelcomeScreen,
        │   │                       # InputToolbar
        │   ├── chunks/             # ChunkRenderer + 15 chunk components:
        │   │                       # AnswerChunk, SqlChunk, ToolCallChunk,
        │   │                       # ToolResultChunk, StatusChunk, ErrorChunk,
        │   │                       # ClarificationChunk, InsightChunk,
        │   │                       # StatsContextChunk, ThinkingTrace,
        │   │                       # TraceModal, ChartBlock, DataTable,
        │   │                       # CitationLink
        │   ├── layout/             # AppShell, Header, LeftSidebar,
        │   │                       # RightSidebar, UserMenu, DatasetSelector
        │   ├── sidebar/            # ConversationList, ConversationItem,
        │   │                       # SearchResults, ProcessSteps, StepItem
        │   ├── sql/                # SqlExecutor, ChartConfigurator
        │   ├── insights/           # InsightBell, InsightPopover, InsightCard,
        │   │                       # InsightAllModal
        │   ├── automations/        # AutomationList, AutomationCard,
        │   │                       # WorkflowBuilder, WorkflowCanvas,
        │   │                       # WorkflowSidebar, SqlBlockNode,
        │   │                       # SqlEditorModal, TriggerConditionBuilder,
        │   │                       # TriggerTemplatePicker, SchedulePicker,
        │   │                       # RunHistory, RunDetailModal,
        │   │                       # AiSqlGenerator, ConditionRow
        │   ├── notifications/      # NotificationBell, NotificationPopover,
        │   │                       # NotificationCard, NotificationList,
        │   │                       # NotificationDetailModal, NotificationAllModal
        │   ├── dataset/            # DatasetViewer
        │   ├── sample-questions/   # SampleQuestionsModal
        │   ├── admin/              # FeatureToggles, BrandingEditor,
        │   │                       # UserOrgMappings, AdminDomainEditor,
        │   │                       # ConversationViewer
        │   └── ui/                 # 30+ shadcn/Radix components
        │
        ├── hooks/
        │   ├── use-sse-chat.ts     # SSE streaming orchestration
        │   ├── use-client-config.ts # Org config + feature flags
        │   ├── use-health-check.ts # Backend health polling
        │   ├── use-theme.ts        # Dark/light mode toggle
        │   ├── use-syntax-theme.ts # Code syntax highlighting theme
        │   ├── use-auto-scroll.ts  # Auto-scroll to bottom
        │   └── use-media-query.ts  # Mobile detection
        │
        ├── stores/
        │   ├── auth-store.ts       # Auth state (login, register, logout)
        │   ├── chat-store.ts       # Chat state (conversations, streaming, steps)
        │   ├── settings-store.ts   # Model settings (provider, model, agent mode)
        │   ├── client-config-store.ts  # Org config (features, branding)
        │   ├── insight-store.ts    # Insights (fetch, bookmark, delete)
        │   ├── automation-store.ts # Automations (CRUD, workflow builder, triggers)
        │   └── notification-store.ts  # Notifications (fetch, read, count)
        │
        ├── lib/
        │   ├── api.ts              # Fetch wrapper with credentials
        │   ├── sse-client.ts       # SSE stream reader + microtask batching
        │   ├── chunk-parser.ts     # JSON parsing + tool result extraction
        │   ├── chart-detector.ts   # Auto chart type + state abbreviation
        │   ├── sql-utils.ts        # Table extraction for workflow edges
        │   ├── automation-utils.ts # Automation helper functions
        │   ├── export-report.ts    # PDF/CSV export
        │   ├── sample-questions.ts # Sample question data
        │   ├── model-utils.ts      # Model name formatting
        │   ├── constants.ts        # API URL, suggested questions
        │   └── utils.ts            # cn() class merge utility
        │
        └── types/
            ├── chat.ts             # ChatChunk, Message, Conversation, AgentStep,
            │                       # OrchestratorPlan, AgentTrace, EnrichmentTrace
            ├── admin.ts            # FeatureToggles, OrgConfig, Branding
            ├── api.ts              # QueryResult, QueryError
            ├── automation.ts       # Automation, AutomationRun, TriggerCondition,
            │                       # WorkflowBlock, WorkflowEdge, Notification
            └── insight.ts          # Insight
```

---

*Last updated: Mar 2, 2026*
