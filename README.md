# InsightXpert

Conversational AI system that enables non-technical business leaders to query digital payment transaction data using natural language and receive accurate, well-explained insights — built for the **Techfest 2025-26 Leadership Analytics Challenge** at IIT Bombay.

## Problem

Business leaders (product managers, operations heads, risk officers) need data-driven insights from payment transaction data but lack SQL or analytics expertise. InsightXpert bridges this gap through a conversational interface that translates natural language questions into data queries and returns clear, actionable answers.

## How It Works

```
User Question (natural language)
        │
        ▼
┌─────────────────────┐
│  RAG Retrieval       │  ← Similar past queries, schema, documentation
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  LLM + Tool Loop     │  ← Gemini generates SQL, calls tools iteratively
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  SQL Execution       │  ← Safe SELECT-only execution with row limits
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  Answer Generation   │  ← Evidence-backed, layered response
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  SSE Streaming       │  ← Real-time chunks to frontend
└────────┘
```

## Supported Query Types

| Type | Example |
|------|---------|
| **Descriptive** | "What is the average transaction amount for bill payments?" |
| **Comparative** | "How do failure rates compare between Android and iOS users?" |
| **Temporal** | "What are the peak transaction hours for food delivery?" |
| **Segmentation** | "Which age group uses P2P transfers most frequently?" |
| **Correlation** | "Is there a relationship between network type and transaction success?" |
| **Risk Analysis** | "What percentage of high-value transactions are flagged for review?" |

## Dataset

250,000 synthetic Indian digital payment transactions with 17 dimensions:

| Category | Fields |
|----------|--------|
| Transaction | `transaction_id`, `timestamp`, `transaction_type` (P2P, P2M, Bill, Recharge), `amount_inr`, `transaction_status` |
| Merchant | `merchant_category` (Food, Grocery, Fuel, Entertainment, Shopping, Healthcare, Education, Transport, Utilities, Other) |
| Parties | `sender_bank`, `receiver_bank`, `sender_state`, `sender_age_group`, `receiver_age_group` |
| Device | `device_type` (Android, iOS, Web), `network_type` (4G, 5G, WiFi, 3G) |
| Risk | `fraud_flag` (0 = not flagged, 1 = flagged for review) |
| Derived | `hour_of_day`, `day_of_week`, `is_weekend` |

## Tech Stack

### Backend
| Layer | Choice | Notes |
|-------|--------|-------|
| **Framework** | FastAPI | SSE streaming, async |
| **LLM** | Google Gemini (`google-genai`) | Primary. Ollama as local dev fallback |
| **Vector Store** | ChromaDB | Embedded, persistent, zero-config |
| **Database** | SQLite via SQLAlchemy | 250K rows, 80MB, 8 indices |
| **Language** | Python 3.11+ | hatchling build system |

### Frontend
| Layer | Choice | Notes |
|-------|--------|-------|
| **Framework** | Next.js 16 (App Router) | React 19 |
| **UI Components** | Radix UI + Shadcn | Accessible primitives |
| **Styling** | Tailwind CSS 4 | Utility-first |
| **State** | Zustand | Persistent to localStorage |
| **Animation** | Framer Motion | Sidebar transitions |
| **Charts** | Recharts | Data visualization |
| **Streaming** | Custom SSE client | Real-time chunk rendering |

## Project Structure

```
InsightXpert/
├── ARCHITECTURE.md              # Technical blueprint & design decisions
├── CLAUDE.md                    # AI assistant instructions
├── README.md
├── .env.example
├── prd/                         # Problem statement & question bank
├── postman/                     # API collection
│
├── backend/
│   ├── pyproject.toml           # Python 3.11+, hatchling build
│   ├── generate_data.py         # 250K transaction generator (seed=42)
│   ├── insightxpert.db          # SQLite DB (80MB, 250K rows)
│   ├── chroma_data/             # ChromaDB persistent store
│   │
│   ├── src/insightxpert/
│   │   ├── main.py              # FastAPI app + async lifespan
│   │   ├── config.py            # Pydantic Settings (LLM, DB, limits)
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py        # /chat (SSE), /chat/poll, /train, /schema, /health, /feedback
│   │   │   └── models.py        # ChatRequest, ChatChunk, FeedbackRequest, etc.
│   │   │
│   │   ├── agents/
│   │   │   ├── analyst.py       # Core agent loop (RAG + LLM + tools, error recovery)
│   │   │   ├── tool_base.py     # Tool ABC, ToolContext, ToolRegistry
│   │   │   ├── tools.py         # RunSqlTool, GetSchemaTool, SearchSimilarTool
│   │   │   └── orchestrator.py  # Multi-agent routing (stub)
│   │   │
│   │   ├── prompts/
│   │   │   ├── __init__.py      # Jinja2 template loader (render function)
│   │   │   └── analyst_system.j2 # Analyst system prompt template
│   │   │
│   │   ├── llm/
│   │   │   ├── base.py          # LLMProvider protocol
│   │   │   ├── factory.py       # Registry-based provider factory (create_llm)
│   │   │   ├── gemini.py        # Google Gemini provider
│   │   │   └── ollama.py        # Ollama local provider (120s timeout)
│   │   │
│   │   ├── db/
│   │   │   ├── connector.py     # SQLAlchemy wrapper (execute, row limits)
│   │   │   └── schema.py        # DDL introspection
│   │   │
│   │   ├── rag/
│   │   │   ├── base.py          # VectorStoreBackend protocol
│   │   │   ├── store.py         # ChromaVectorStore: 4 collections (qa, ddl, docs, findings)
│   │   │   └── memory.py        # InMemoryVectorStore (for testing)
│   │   │
│   │   ├── memory/
│   │   │   └── conversation_store.py  # In-memory LRU + TTL conversation history
│   │   │
│   │   ├── auth/
│   │   │   ├── models.py        # User, ConversationRecord, MessageRecord, FeedbackRecord
│   │   │   └── conversation_store.py  # Persistent CRUD + get_or_create_conversation
│   │   │
│   │   ├── observability/       # Tracer + store (stubs for Day 2+)
│   │   │
│   │   └── training/
│   │       ├── trainer.py       # RAG bootstrap (DDL + docs + 12 QA pairs)
│   │       ├── schema.py        # DDL constant (17-column transactions table)
│   │       ├── documentation.py # Business context & column descriptions
│   │       └── queries.py       # 12 example Q→SQL pairs (6 categories)
│   │
│   └── tests/                   # Agent, DB, RAG tests (pytest-asyncio)
│
└── frontend/
    ├── package.json             # Next.js 16, React 19, Zustand, Shadcn
    └── src/
        ├── app/                 # Next.js App Router (layout, page)
        ├── components/
        │   ├── chat/            # ChatPanel, MessageBubble, MessageActions, MessageInput, MessageList, WelcomeScreen
        │   ├── chunks/          # ChunkRenderer, StatusChunk, SqlChunk, ToolResultChunk, AnswerChunk, ErrorChunk
        │   ├── layout/          # AppShell, Header, UserMenu, LeftSidebar, RightSidebar
        │   ├── sidebar/         # ConversationList, ProcessSteps, StepItem
        │   └── ui/              # Shadcn primitives (button, card, avatar, input, etc.)
        ├── hooks/               # useSSEChat, useAutoScroll, useMediaQuery
        ├── lib/                 # SSE client, chunk parser, chart detector, constants
        ├── stores/              # Zustand chat store (conversations, agent steps)
        └── types/               # TypeScript interfaces (ChatChunk, Message, AgentStep)
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+
- A [Google Gemini API key](https://aistudio.google.com/apikey) (or [Ollama](https://ollama.com/) running locally)

## Setup

### 1. Clone

```bash
git clone <repo-url>
cd InsightXpert
```

### 2. Backend

```bash
cd backend

# Create venv and install dependencies (uses uv.lock for reproducible builds)
uv sync

# Copy env template and fill in your values
cp .env.example .env.local
```

Edit `backend/.env.local` — at minimum set:

```
GEMINI_API_KEY=your-key-here
SECRET_KEY=some-random-string
```

To use Ollama instead of Gemini, set `LLM_PROVIDER=ollama`.

```bash
# Generate the transaction dataset (first time only)
python generate_data.py

# Start the API server
uv run python -m insightxpert.main
# → http://localhost:8000
```

On first startup the backend auto-creates SQLite databases and bootstraps the RAG vector store.

### 3. Frontend

```bash
cd frontend

# Install dependencies (uses package-lock.json for reproducible builds)
npm ci

# Start the dev server
npm run dev
# → http://localhost:3000
```

The frontend connects to the backend at `http://localhost:8000` (configured in `frontend/.env.local`).

## Key Design Decisions

**From-scratch agent engine** — Vanna was replaced with a custom ~600-line engine for full control over multi-agent orchestration, explainability layers, and SSE streaming.

**Design patterns for extensibility:**
- **LLM Factory** (`llm/factory.py`) — Registry-based provider creation via `create_llm(provider, settings)`. Adding a new LLM backend requires only registering a factory function; no if/else chains to touch.
- **Tool ABC + ToolRegistry** (`agents/tool_base.py`) — Each tool is a class with `name`, `description`, `get_args_schema()`, and `execute()`. The `ToolRegistry` manages dispatch, schema generation, and error handling (sanitized errors only — no tracebacks leaked to LLM/user). New tools are added by subclassing `Tool` and calling `registry.register()`.
- **VectorStoreBackend Protocol** (`rag/base.py`) — Runtime-checkable protocol decouples all RAG consumers from ChromaDB. `InMemoryVectorStore` provides a zero-dependency backend for testing. Protocol conformance verified at import time via `issubclass` assertions.
- **Jinja2 Prompt Templates** (`prompts/analyst_system.j2`) — System prompt extracted into a Jinja2 template with conditional sections for RAG context (similar QA, DDL, docs, findings). Template rendering via `prompts.render()`.

**Explainability-first approach** — Every response includes:
1. A plain-language summary using business vocabulary
2. Supporting statistics and evidence
3. Data provenance (row count, scope)
4. Confidence caveats for small sample sizes
5. Follow-up suggestions for deeper analysis

**Error resilience:**
- LLM call failures (network errors, model not found, timeouts) are caught and surfaced as chat error messages instead of crashing the stream
- Ollama provider has a 120s timeout; model existence is validated on provider switch (HTTP 503 with clear message)
- Conversation persistence uses `get_or_create_conversation` to bridge frontend-generated IDs with backend storage

**Message interactions:**
- Copy prompt/response, thumbs up/down feedback, retry last message
- Feedback persisted via `POST /api/feedback` with rating and optional comment
- Old conversations lazy-load messages on click from `GET /api/conversations/{id}`

**Guardrails:**
- No causal claims — correlation only
- `fraud_flag` = flagged for review, not confirmed fraud
- Dual SQL write protection: regex blocklist + SQLite `PRAGMA query_only` at engine level; row limits, timeouts
- No user-level profiling (no `user_id` in dataset)
- Insights are directional (synthetic data)

## Evaluation Criteria

| Criterion | Weight |
|-----------|--------|
| Insight Accuracy | 30% |
| Query Understanding | 25% |
| Explainability | 20% |
| Conversational Quality | 15% |
| Innovation & Technical Implementation | 10% |

## Team

| Member | Role |
|--------|------|
| **Nachiket** | System architecture, UI/UX, LLM pipeline (model selection, prompt engineering, query understanding, SQL generation, response synthesis, validation) |
| **Arush** | Data layer, SQL execution engine, API endpoints, deployment |

## License

This project is part of the Techfest 2025-26 competition at IIT Bombay.
