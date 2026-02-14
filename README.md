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
│   │   │   ├── routes.py        # /chat (SSE), /chat/poll, /train, /schema, /health
│   │   │   └── models.py        # ChatRequest, ChatChunk, TrainRequest, etc.
│   │   │
│   │   ├── agents/
│   │   │   ├── analyst.py       # Core agent loop (RAG + LLM + tools)
│   │   │   ├── tools.py         # run_sql, get_schema, search_similar
│   │   │   └── orchestrator.py  # Multi-agent routing (stub)
│   │   │
│   │   ├── llm/
│   │   │   ├── base.py          # LLMProvider protocol
│   │   │   ├── gemini.py        # Google Gemini provider
│   │   │   └── ollama.py        # Ollama local provider
│   │   │
│   │   ├── db/
│   │   │   ├── connector.py     # SQLAlchemy wrapper (execute, row limits)
│   │   │   └── schema.py        # DDL introspection
│   │   │
│   │   ├── rag/
│   │   │   └── store.py         # ChromaDB: 4 collections (qa, ddl, docs, findings)
│   │   │
│   │   ├── memory/
│   │   │   └── conversation_store.py  # In-memory LRU + TTL conversation history
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
        │   ├── chat/            # ChatPanel, MessageBubble, MessageInput, MessageList, WelcomeScreen
        │   ├── chunks/          # ChunkRenderer, StatusChunk, SqlChunk, ToolResultChunk, AnswerChunk, ErrorChunk
        │   ├── layout/          # AppShell, Header, LeftSidebar, RightSidebar
        │   ├── sidebar/         # ConversationList, ProcessSteps, StepItem
        │   └── ui/              # Shadcn primitives (button, card, input, etc.)
        ├── hooks/               # useSSEChat, useAutoScroll, useMediaQuery
        ├── lib/                 # SSE client, chunk parser, chart detector, constants
        ├── stores/              # Zustand chat store (conversations, agent steps)
        └── types/               # TypeScript interfaces (ChatChunk, Message, AgentStep)
```

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd InsightXpert

# --- Backend ---
cd backend
uv sync                          # Install Python dependencies
python generate_data.py          # Generate 250K transactions → insightxpert.db
export GEMINI_API_KEY="your-key" # Or add to .env.local
python -m insightxpert.main      # Start API server → http://localhost:8000

# --- Frontend ---
cd ../frontend
npm install                      # Install Node dependencies
npm run dev                      # Start dev server → http://localhost:3000
```

## Key Design Decisions

**From-scratch agent engine** — Vanna was replaced with a custom ~600-line engine for full control over multi-agent orchestration, explainability layers, and SSE streaming.

**Explainability-first approach** — Every response includes:
1. A plain-language summary using business vocabulary
2. Supporting statistics and evidence
3. Data provenance (row count, scope)
4. Confidence caveats for small sample sizes
5. Follow-up suggestions for deeper analysis

**Guardrails:**
- No causal claims — correlation only
- `fraud_flag` = flagged for review, not confirmed fraud
- SELECT-only SQL enforcement, row limits, timeouts
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
