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
2. Connects to SQLite database
3. Initializes ChromaDB vector store
4. Creates LLM provider (Gemini or Ollama)
5. Creates auth database tables and seeds admin user
6. Initializes both conversation stores
7. Bootstraps RAG with training data (DDL, docs, 12+ Q→SQL pairs)
8. Registers 4 routers: API, Auth, Admin, Client Config

### 4.2 Agent Loop (`agents/analyst.py`)

The core ~600-line engine that replaced Vanna. It's an async generator that yields `ChatChunk` objects:

```
analyst_loop(question, settings, llm, db, rag, history, tool_registry)
  → AsyncGenerator[ChatChunk]
```

**Error handling:** All LLM calls are wrapped in try/except. Failures yield error chunks instead of crashing the stream. The loop enforces a max iteration limit (default 10) to prevent infinite tool-calling cycles.

### 4.3 Tools (`agents/tool_base.py`, `agents/tools.py`)

**Abstract Base Class pattern:**
- `Tool` ABC: `name`, `description`, `get_args_schema()`, `execute()`
- `ToolRegistry`: manages tools, generates JSON schemas for the LLM, executes with error handling
- Error sanitization: tool errors return clean messages, never stack traces

**3 tools:**
| Tool | Purpose | Key Safety |
|------|---------|------------|
| `RunSqlTool` | Execute SELECT queries | Row limit (1000), timeout (30s), read-only |
| `GetSchemaTool` | Inspect table DDL | Read-only introspection |
| `SearchSimilarTool` | Query ChromaDB knowledge base | Read-only search |

**Statistical tools** (`agents/stat_tools.py`): Additional tools for the statistician agent:
- `compute_descriptive_stats` — count, mean, std, min, quartiles, max, skewness, kurtosis
- `test_hypothesis` — chi-squared, t-test, Mann-Whitney, ANOVA, z-proportion
- `compute_correlation` — Pearson, Spearman, Kendall with p-values
- `fit_distribution` — normal, exponential, lognormal, gamma, Weibull ranking by KS-test

### 4.4 LLM Providers (`llm/`)

**Protocol-based design:**
```
LLMProvider protocol:
  .model → str
  .chat(messages, tools) → LLMResponse
  .chat_stream(messages, tools) → AsyncGenerator[LLMChunk]
```

**Factory pattern:** `create_llm("gemini", settings)` uses a registry of factory functions. No if/else chains. Adding a new provider = write the class + register a factory.

**Two providers:**
- **Gemini** (`gemini.py`) — Uses `google-genai` async client. Handles function calling, streaming, multipart content.
- **Ollama** (`ollama.py`) — Uses `ollama` async client with 120s timeout. Same protocol, local development fallback.

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

Jinja2 templates rendered per query:
- `analyst_system.j2` — Main analyst prompt (identity, DDL, docs, rules, RAG context, visualization guidelines)
- `statistician_system.j2` — Statistical analysis prompt (hypothesis testing rules, response structure)

Conditional sections inject RAG context only when matches are found:
```jinja2
{% if similar_qa %}
## Similar Past Queries
{% for item in similar_qa %}{{ item.document }}{% endfor %}
{% endif %}
```

### 4.7 Admin System (`admin/`)

Multi-tenant configuration system:
- **Feature toggles:** SQL executor, model switching, RAG training, chart rendering, conversation export, agent process sidebar
- **Org branding:** Custom display name, logo URL, CSS theme variable overrides
- **User-org mappings:** Email → organization assignment
- **Admin domains:** Email domains that grant admin access

Stored as JSON on disk (`config/client-configs.json`). Admin endpoints require admin user.

---

## 5. Frontend Architecture

**Tech:** Next.js 16 (App Router), React 19, TypeScript, Zustand, Tailwind CSS 4, shadcn/ui, Recharts, Framer Motion

### 5.1 Pages

| Route | Component | Auth |
|-------|-----------|------|
| `/` | Chat interface (AppShell + ChatPanel) | Required (AuthGuard) |
| `/login` | Email/password form | Public |
| `/admin` | Admin panel (feature toggles, branding, user mappings) | Admin only |

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

### 5.3 State Management (4 Zustand Stores)

| Store | State | Key Actions |
|-------|-------|-------------|
| **auth-store** | `user`, `isLoading`, `error` | `login()`, `logout()`, `checkAuth()` |
| **chat-store** | `conversations[]`, `activeConversationId`, `isStreaming`, `agentSteps[]`, sidebar states | `newConversation()`, `addUserMessage()`, `appendChunk()`, `finishStreaming()`, `loadConversationMessages()` |
| **settings-store** | `currentProvider`, `currentModel`, `providers[]`, `agentMode` | `fetchConfig()`, `switchModel()`, `setAgentMode()` |
| **client-config-store** | `config` (org settings), `isAdmin`, `orgId` | `fetchConfig()` (applies branding CSS vars, sets document title) |

### 5.4 SSE Streaming (`hooks/use-sse-chat.ts`)

The core streaming hook orchestrates:
1. Creates/reuses conversation
2. Opens SSE connection with POST body (not GET — supports request body)
3. Parses newline-delimited JSON chunks with 16ms stagger delay for smooth animation
4. Updates Zustand stores in real-time
5. Manages agent step timeline (pending → running → done/error)
6. Handles AbortController for stop functionality

### 5.5 Chunk Rendering (`components/chunks/`)

Each SSE chunk type has a dedicated React component:

| Chunk | Component | What It Renders |
|-------|-----------|-----------------|
| `status` | StatusChunk | Spinner + label (e.g., "Searching knowledge base...") |
| `tool_call` | ToolCallChunk | Pulsing dot + tool name |
| `sql` | SqlChunk | Collapsible SQL with syntax highlighting (vs2015 theme) + copy button |
| `tool_result` | ToolResultChunk | Collapsible data table + auto-detected chart |
| `answer` | AnswerChunk | GitHub-flavored Markdown via react-markdown |
| `error` | ErrorChunk | Red error card with description |

### 5.6 Chart Auto-Detection (`lib/chart-detector.ts`)

Heuristic-based chart type selection from query results:
- **Pie:** 2-10 rows, 1 category + 1 numeric column (parts of a whole)
- **Grouped Bar:** 2 category columns + 1+ numeric (cross-tabulations)
- **Line:** Temporal column detected by name (date, month, year, quarter, etc.)
- **Bar:** 1+ category + 1+ numeric, default for most aggregations
- **Table:** Fallback for single-row results, wide tables, or no clear chart fit

Also auto-abbreviates Indian state names to 2-letter RTO codes (Maharashtra → MH) for chart readability.

### 5.7 Key UI Features

- **Welcome Screen:** Logo, subtitle, centered input, 3 animated suggested questions
- **Message Actions:** Copy prompt/response, thumbs up/down feedback with optional comment, retry last message
- **Model Selector:** Breadcrumb-style `Provider / Model` dropdowns in header with runtime switching
- **SQL Executor:** Right-side sheet panel with read-only SQL editor, Ctrl/Cmd+Enter execution, results table with stats
- **Conversation Management:** Create, rename, delete, search conversations in left sidebar
- **Theme Toggle:** Dark/light mode with localStorage persistence
- **Agent Timeline:** Real-time process steps with expandable details (LLM reasoning, SQL, results, RAG context)

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

### 6.2 Auth Database

**File:** `insightxpert_auth.db` (SQLite)

**Tables:**
- `users` — id (UUID), email (unique), hashed_password, is_active, is_admin, created_at, last_active
- `conversations` — id, user_id (FK), title, is_starred, created_at, updated_at
- `messages` — id, conversation_id (FK), role, content, chunks_json, feedback, feedback_comment, created_at

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
| **Persistent** (SQLite) | Full history replay | Unlimited | `insightxpert_auth.db` |

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

- **Feature Toggles:** 6 boolean flags control which features are visible per organization
  - sql_executor, model_switching, rag_training, chart_rendering, conversation_export, agent_process_sidebar
- **Org Branding:** Custom display name, logo URL, CSS theme color overrides
- **User-Org Mappings:** Map email addresses to organizations
- **Admin Domains:** Email domains that automatically grant admin access

Admin endpoints (`/api/admin/*`) require admin user. Public endpoint (`/api/client-config`) returns resolved config for the current user based on their org mapping.

Frontend admin page at `/admin` provides UI for all configuration with guards that redirect non-admins.

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

- Analyst agent with full tool-calling loop and error recovery
- Tool ABC + ToolRegistry with 3 tools (run_sql, get_schema, search_similar)
- Statistical tools (descriptive stats, hypothesis testing, correlation, distribution fitting)
- Gemini + Ollama LLM providers with runtime switching
- Database connector with dual read-only enforcement
- ChromaDB vector store with 4 collections and auto-learning
- JWT + bcrypt authentication with persistent conversations
- Admin system with feature toggles, org branding, user-org mappings
- 20+ API endpoints
- Full frontend with SSE streaming, agent timeline, chart auto-detection
- 3-column responsive layout with dark/light theme
- 4 Zustand stores (auth, chat, settings, client-config)
- SQL executor panel
- CI/CD with GitHub Actions, Cloud Run, Firebase Hosting

### Planned/Stubbed

- Multi-agent orchestrator (6-line stub, no routing logic)
- Statistician agent integration into pipeline
- Creative Narrator agent
- Anomaly Detector (background scan)
- Observability dashboard (tracer + store are stubs)
- Ambiguity detection (ask clarifying questions for vague queries)

---

## 14. File Map

```
InsightXpert/
├── README.md                       # Project overview & setup
├── ARCHITECTURE.md                 # Technical blueprint & design decisions
├── DEPLOY.md                       # Deployment guide
├── WALKTHROUGH.md                  # This file
├── CLAUDE.md                       # AI assistant instructions
├── firebase.json                   # Firebase Hosting config
├── .env.example                    # Environment variable template
│
├── .github/workflows/
│   ├── deploy.yml                  # Production CI/CD
│   └── preview.yml                 # PR preview CI/CD
│
├── prd/QuestionBank/               # Problem statement & evaluation criteria
│   ├── 01_problem_understanding.md
│   ├── 02_leadership_questions.md
│   ├── 03_data_computation.md
│   ├── 04_assumptions.md
│   ├── 05_explainability.md
│   ├── 06_scope_exclusions.md
│   └── 07_team_execution_plan.md
│
├── postman/                        # API collection for testing
│
├── backend/
│   ├── pyproject.toml              # Python deps (hatchling, Python 3.11+)
│   ├── uv.lock                     # Locked dependency versions
│   ├── Dockerfile                  # Cloud Run container
│   ├── generate_data.py            # 250K transaction data generator
│   ├── seed_turso.py               # Cloud Turso DB seeder
│   ├── insightxpert.db             # SQLite main DB (80MB, 250K rows)
│   ├── insightxpert_auth.db        # SQLite auth + conversations DB
│   ├── chroma_data/                # ChromaDB persistent vector store
│   ├── config/client-configs.json  # Admin configuration
│   │
│   ├── tests/
│   │   ├── conftest.py             # Test fixtures
│   │   ├── test_agent.py           # Agent loop tests
│   │   ├── test_db.py              # Database tests
│   │   ├── test_rag.py             # RAG tests
│   │   └── test_statistician.py    # Stats tools tests
│   │
│   └── src/insightxpert/
│       ├── main.py                 # FastAPI app entry point
│       ├── config.py               # Pydantic Settings
│       │
│       ├── api/
│       │   ├── routes.py           # 20+ API endpoints
│       │   └── models.py           # Request/response models
│       │
│       ├── agents/
│       │   ├── analyst.py          # Core agent loop
│       │   ├── tool_base.py        # Tool ABC + ToolRegistry
│       │   ├── tools.py            # RunSql, GetSchema, SearchSimilar
│       │   ├── stat_tools.py       # Statistical analysis tools
│       │   └── orchestrator.py     # Multi-agent routing (stub)
│       │
│       ├── prompts/
│       │   ├── __init__.py         # Jinja2 template loader
│       │   ├── analyst_system.j2   # Analyst system prompt
│       │   └── statistician_system.j2  # Statistician system prompt
│       │
│       ├── llm/
│       │   ├── base.py             # LLMProvider protocol
│       │   ├── factory.py          # Registry-based factory
│       │   ├── gemini.py           # Google Gemini provider
│       │   └── ollama.py           # Ollama local provider
│       │
│       ├── db/
│       │   ├── connector.py        # SQLAlchemy wrapper
│       │   └── schema.py           # DDL introspection
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
│       │   ├── routes.py           # Login, logout, me
│       │   ├── models.py           # User, Conversation, Message ORM
│       │   ├── security.py         # JWT + bcrypt
│       │   ├── dependencies.py     # get_current_user
│       │   ├── conversation_store.py   # Persistent CRUD
│       │   └── seed.py             # Admin user bootstrap
│       │
│       ├── admin/
│       │   ├── routes.py           # Admin endpoints
│       │   ├── config_store.py     # JSON config file management
│       │   └── models.py           # FeatureToggles, OrgConfig, etc.
│       │
│       ├── training/
│       │   ├── trainer.py          # RAG bootstrap
│       │   ├── schema.py           # DDL constant
│       │   ├── documentation.py    # Business context
│       │   └── queries.py          # 12+ example Q→SQL pairs
│       │
│       └── observability/          # Stubs for future tracing
│           ├── tracer.py
│           └── store.py
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
        │   ├── layout.tsx          # Root layout (fonts, metadata)
        │   ├── globals.css         # Tailwind 4 + OKLch + glassmorphism
        │   ├── page.tsx            # Home (AuthGuard + AppShell + ChatPanel)
        │   ├── login/page.tsx      # Login form
        │   └── admin/
        │       ├── layout.tsx      # Admin layout with guards
        │       └── page.tsx        # Admin panel
        │
        ├── components/
        │   ├── auth/auth-guard.tsx
        │   ├── chat/               # ChatPanel, MessageList, MessageBubble,
        │   │                       # MessageInput, MessageActions, WelcomeScreen,
        │   │                       # InputToolbar
        │   ├── chunks/             # ChunkRenderer, StatusChunk, SqlChunk,
        │   │                       # ToolResultChunk, ToolCallChunk, AnswerChunk,
        │   │                       # ErrorChunk, ChartBlock, DataTable
        │   ├── layout/             # AppShell, Header, LeftSidebar,
        │   │                       # RightSidebar, UserMenu
        │   ├── sidebar/            # ConversationList, ConversationItem,
        │   │                       # SearchResults, ProcessSteps, StepItem
        │   ├── sql/sql-executor.tsx
        │   ├── admin/              # FeatureToggles, BrandingEditor,
        │   │                       # UserOrgMappings, AdminDomainEditor
        │   └── ui/                 # 14+ shadcn/Radix components
        │
        ├── hooks/
        │   ├── use-sse-chat.ts     # SSE streaming orchestration
        │   ├── use-client-config.ts # Org config + feature flags
        │   ├── use-theme.ts        # Dark/light mode toggle
        │   ├── use-auto-scroll.ts  # Auto-scroll to bottom
        │   └── use-media-query.ts  # Mobile detection
        │
        ├── stores/
        │   ├── auth-store.ts       # Zustand auth state
        │   ├── chat-store.ts       # Zustand chat state
        │   ├── settings-store.ts   # Zustand model settings
        │   └── client-config-store.ts  # Zustand org config
        │
        ├── lib/
        │   ├── api.ts              # Fetch wrapper with credentials
        │   ├── sse-client.ts       # SSE stream reader + chunk stagger
        │   ├── chunk-parser.ts     # JSON parsing + tool result extraction
        │   ├── chart-detector.ts   # Auto chart type + state abbreviation
        │   ├── model-utils.ts      # Model name formatting
        │   ├── constants.ts        # API URL, suggested questions
        │   └── utils.ts            # cn() class merge utility
        │
        └── types/
            ├── chat.ts             # ChatChunk, Message, Conversation, AgentStep
            └── admin.ts            # FeatureToggles, OrgConfig, Branding
```

---

*Last updated: Feb 17, 2026*
