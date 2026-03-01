# InsightXpert

**AI-powered data analyst for non-technical business leaders.**
Ask questions in plain English. Get data-backed answers from 250K payment transactions — no SQL required.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15%2F16-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Google Gemini](https://img.shields.io/badge/Gemini-2.5--flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

Built for the **Techfest 2025-26 Leadership Analytics Challenge** at IIT Bombay.

---

## What Is This?

InsightXpert lets product managers, operations heads, and risk officers ask questions like:

> *"Which age group drives the most P2P transaction volume on weekends?"*
> *"Are 5G users more likely to complete high-value transactions successfully?"*
> *"Flag any merchant categories with unusually high fraud review rates."*

...and receive cited, data-grounded answers with confidence caveats — no SQL or analytics experience required.

Under the hood, natural language is translated to SQL, executed against a 250K-row SQLite database of synthetic Indian digital payment transactions, and synthesized into a layered explanation. In **agentic mode**, a multi-agent pipeline automatically enriches the answer with comparative context, temporal trends, root-cause hypotheses, and segmentation breakdowns.

---

## Pipeline

### Basic Mode

```
User Question (natural language)
        │
        ▼
┌────────────────────────┐
│  RAG Retrieval          │  ChromaDB — similar past Q→SQL, schema DDL,
│                         │  column docs, saved findings
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Analyst Agent          │  Gemini renders a Jinja2 system prompt,
│  (LLM + Tool Loop)      │  calls run_sql / get_schema / search_similar
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  SQL Execution          │  Read-only SQLite, row-limited, timeout-guarded
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Answer Synthesis       │  Plain-language summary, evidence, provenance,
│                         │  caveats, follow-up suggestions
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  SSE Streaming          │  Real-time chunk delivery to the frontend
└────────────────────────┘
```

### Agentic Mode (multi-agent enrichment)

```
Phase 1: Analyst answers the question immediately (user sees results)
            │
            ▼
Phase 2: Evaluator LLM scores the answer — decides which enrichment
         categories are worthwhile:
           comparative_context | temporal_trend | root_cause | segmentation
            │
            ▼
Phase 3: DAG Executor runs sub-agents in parallel (respecting dependencies):
           sql_analyst   — follow-up SQL queries
           quant_analyst — scipy/numpy/pandas statistical tests
            │
            ▼
Phase 4: Response Synthesizer combines all results into a cited insight,
         numbered citation links [1] [2] ... linking to enrichment sources
            │
            ▼
Phase 5: Insight persisted to DB → surfaces in the Insights panel (bell icon)
```

---

## Features

### Chat & Analysis

| Feature | Description |
|---------|-------------|
| Natural language to SQL | Ask any question; the agent generates and runs SQL |
| Two answer modes | **Basic** (fast, analyst only) and **Agentic** (deep, multi-agent) |
| Streaming responses | SSE delivers answer chunks in real-time as the LLM generates them |
| Multi-turn conversations | Full conversation history with persistent storage |
| Clarification system | LLM asks a targeted follow-up before answering ambiguous questions |
| Force-tool-use guardrail | LLM must query the database before answering — no hallucinations |
| Pre-computed stats injection | Common metric answers accelerated via cached statistics context |
| RAG self-improvement | Successful Q→SQL pairs auto-saved to ChromaDB for future retrieval |
| Thinking trace | Collapsible modal showing each sub-agent's SQL, results, and reasoning |
| Citation links | Numbered `[1]` `[2]` inline citations in insights linking to enrichment sources |
| Feedback | Thumbs up/down + optional comment, persisted to DB |
| Observability metrics | Token count and generation time emitted as a metrics chunk per response |

### Conversation Management

| Feature | Description |
|---------|-------------|
| Conversation list | Left sidebar with all past conversations |
| Rename | Inline rename from sidebar or header |
| Star / favourite | Pin important conversations to the top |
| Delete | Single conversation or bulk delete |
| Full-text search | Search across all conversation titles and messages |
| Lazy message loading | Old conversation messages load on click, not on page load |

### SQL Executor

Direct SQL panel with the same read-only protections (regex blocklist + `PRAGMA query_only`). Results displayed as a data table. Streaming CSV export for any result set.

### Dataset Viewer

Browse the raw `transactions` table with sticky opaque headers, click-to-preview row details, and pagination. Includes a dataset description and column-level documentation.

### Dataset Selector

Switch the active dataset at runtime. Each dataset carries its own DDL and documentation fed into the RAG context and system prompt.

### Insights Panel

Persisted AI insights surfaced via a bell notification icon. Each insight has a category badge, a modal drill-down with the full enriched analysis, and citation links to the supporting sub-agent outputs.

### Notifications Panel

System-level notifications with a bell icon. Distinct from the Insights panel.

### Automations

Visual workflow builder for scheduling SQL-based alerts:
- AI-generated SQL from a plain-language description
- Trigger condition editor
- Schedule picker (cron-based)
- DAG canvas visualizing the workflow graph
- Run history with status and output

### Admin Panel

| Section | Description |
|---------|-------------|
| Feature toggles | Enable/disable agentic mode, insights, automations, SQL executor per org |
| Branding editor | Logo, primary colour, app name per tenant |
| User-org mappings | Assign users to organisations |
| Prompt template editor | Edit the Jinja2 system prompt live |
| Domain admin config | Configure allowed email domains |
| Conversation viewer | Read any user's conversations (admin only) |

### LLM Switcher

Switch between Gemini models, Ollama (local), and Vertex AI at runtime — no restart required.

### UI / UX

- Dark and light mode
- Mobile responsive
- Health-check gate: frontend waits for backend `/health` before rendering
- Keyboard shortcuts, auto-scroll, copy-to-clipboard on all code blocks

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+
- A [Google Gemini API key](https://aistudio.google.com/apikey)
  *(or [Ollama](https://ollama.com/) running locally — set `LLM_PROVIDER=ollama`)*

### Backend

```bash
git clone <repo-url>
cd InsightXpert/backend

# Install Python dependencies (reproducible from uv.lock)
uv sync

# Configure environment
cp .env.example .env.local
# Edit .env.local — minimum required:
#   GEMINI_API_KEY=your-key-here
#   SECRET_KEY=some-random-string

# Generate the 250K transaction dataset (first time only, ~30 seconds)
python generate_data.py

# Start the API server
uv run python -m insightxpert.main
# → http://localhost:8000
```

On first startup, SQLite databases are auto-created, the RAG vector store is seeded with DDL + documentation + 12 Q→SQL example pairs, and an admin user is bootstrapped.

### Frontend

```bash
cd InsightXpert/frontend

# Install Node dependencies (reproducible from package-lock.json)
npm ci

# Start the dev server
npm run dev
# → http://localhost:3000
```

The frontend connects to `http://localhost:8000` by default (configure in `frontend/.env.local`).

---

## How It Works

### Basic Mode — Step by Step

1. **RAG retrieval** — ChromaDB searches four collections (Q→SQL pairs, DDL, column docs, saved findings) for the most similar prior context. Top-k results are embedded in the system prompt.

2. **System prompt rendering** — A Jinja2 template (`analyst_system.j2`) combines the schema, column documentation, RAG results, and behavioural instructions into the final prompt. Conditional blocks include or exclude RAG sections based on retrieval quality.

3. **LLM + tool loop** — Gemini receives the rendered prompt and the user's message. It calls tools iteratively:
   - `run_sql` — executes a SELECT query; results returned as truncated JSON rows
   - `get_schema` — returns DDL for a specific table
   - `search_similar` — searches ChromaDB for related past answers

4. **Force-tool-use guardrail** — The agent checks that at least one `run_sql` call was made. If the LLM tries to answer from memory alone, it is forced back into the tool loop.

5. **Answer synthesis** — After the tool loop, the LLM synthesises a final response structured as: plain-language finding → supporting statistics → data provenance (row count, scope) → confidence caveats → follow-up suggestions.

6. **SSE streaming** — Chunks are yielded as server-sent events. The frontend renders each chunk type (status bar, SQL block, data table, chart, rich text) as it arrives.

7. **Background persistence** — `[DONE]` is sent immediately. DB persistence happens in a fire-and-forget background thread so the client sees the end of the response without waiting for the write.

### Agentic Mode — Additional Phases

After Phase 1 (basic answer), the **Evaluator** LLM reads the analyst's response and decides which of four enrichment categories add value:

| Category | What it adds |
|----------|-------------|
| `comparative_context` | Benchmarks the finding against a related group or time period |
| `temporal_trend` | Checks whether the pattern is growing, shrinking, or stable over time |
| `root_cause` | Generates hypotheses for *why* the pattern exists and tests them |
| `segmentation` | Breaks the top-level finding down by age group, device type, region, etc. |

The **DAG Executor** runs approved sub-tasks in parallel (honouring declared dependencies). Each sub-task is either a `sql_analyst` (another SQL query loop) or a `quant_analyst` (scipy/numpy/pandas statistical tests — hypothesis testing, correlation, distribution fitting).

The **Response Synthesizer** merges all sub-results into a single cited insight. Citations are numbered `[1]` `[2]` and link to the enrichment source in the thinking trace.

### RAG Self-Improvement

Every time the agent produces a valid SQL query that the user does not thumbs-down, the Q→SQL pair is stored in ChromaDB. Over time the vector store accumulates organisation-specific phrasing, which improves retrieval accuracy for recurring question patterns.

---

## Dataset Schema

250,000 synthetic Indian digital payment transactions, 17 columns.

| Column | Type | Values / Notes |
|--------|------|---------------|
| `transaction_id` | TEXT | UUID primary key |
| `timestamp` | TEXT | ISO 8601, 2023-01-01 to 2024-12-31 |
| `transaction_type` | TEXT | P2P, P2M, Bill, Recharge |
| `amount_inr` | REAL | ₹1 – ₹100,000 |
| `transaction_status` | TEXT | Success, Failed, Pending |
| `merchant_category` | TEXT | Food, Grocery, Fuel, Entertainment, Shopping, Healthcare, Education, Transport, Utilities, Other |
| `sender_bank` | TEXT | Top Indian banks |
| `receiver_bank` | TEXT | Top Indian banks |
| `sender_state` | TEXT | 28 Indian states + UTs |
| `sender_age_group` | TEXT | 18-25, 26-35, 36-45, 46-55, 55+ |
| `receiver_age_group` | TEXT | 18-25, 26-35, 36-45, 46-55, 55+ |
| `device_type` | TEXT | Android, iOS, Web |
| `network_type` | TEXT | 4G, 5G, WiFi, 3G |
| `fraud_flag` | INTEGER | 0 = not flagged, 1 = flagged for review |
| `hour_of_day` | INTEGER | 0–23 (derived from timestamp) |
| `day_of_week` | INTEGER | 0=Mon … 6=Sun (derived) |
| `is_weekend` | INTEGER | 0 or 1 (derived) |

**Important:** `fraud_flag = 1` means flagged for review by the system, not confirmed fraud. All insights are directional — this is synthetic data.

### Supported Query Types

| Type | Example |
|------|---------|
| Descriptive | "What is the average transaction amount for bill payments?" |
| Comparative | "How do failure rates compare between Android and iOS users?" |
| Temporal | "What are the peak transaction hours for food delivery?" |
| Segmentation | "Which age group uses P2P transfers most frequently?" |
| Correlation | "Is there a relationship between network type and transaction success?" |
| Risk Analysis | "What percentage of high-value transactions are flagged for review?" |

---

## Tech Stack

### Backend

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | FastAPI | Async, SSE streaming, lifespan events |
| Runtime | Python 3.11+, uv | hatchling build, `uv.lock` for reproducible installs |
| LLM — primary | Google Gemini (`google-genai`) | `gemini-2.5-flash` default |
| LLM — local | Ollama | 120s timeout, model existence validated on switch |
| LLM — cloud alt | Vertex AI | Runtime-switchable via LLM Factory |
| Prompt templating | Jinja2 | Conditional RAG sections, no f-string spaghetti |
| Vector store | ChromaDB | Embedded, persistent, 4 collections |
| Database | SQLite via SQLAlchemy | 80MB, 250K rows, 8 indices |
| Auth | JWT + bcrypt | `python-jose`, `passlib` |
| Container | Docker | Cloud Run target |
| DB replication | Litestream | GCS backup on Cloud Run |

### Frontend

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | Next.js 15/16 (App Router) | React 19, TypeScript |
| UI components | Radix UI + Shadcn | Accessible primitives |
| Styling | Tailwind CSS 4 | Utility-first |
| State management | Zustand | Persisted to `localStorage` |
| Animation | Framer Motion | Sidebar transitions, panel reveals |
| Charts | Recharts | Inline data visualisation |
| Streaming | Custom SSE client | Chunk queue, React 18 batched updates |
| Build | Turbopack / Next.js | Firebase Hosting target |

### Infrastructure

| Concern | Technology |
|---------|-----------|
| Frontend hosting | Firebase Hosting |
| Backend hosting | Google Cloud Run |
| CI/CD | GitHub Actions |
| Auth to GCP | Workload Identity Federation (keyless) |
| DB backup | Litestream → GCS |

---

## Project Structure

```
InsightXpert/
├── LICENSE
├── README.md
├── ARCHITECTURE.md          # Technical blueprint & design decisions
├── WALKTHROUGH.md           # Consolidated project walkthrough
├── DEPLOY.md                # Deployment guide (Firebase + Cloud Run)
├── firebase.json            # Firebase Hosting config (API rewrite → Cloud Run)
├── prd/                     # Problem statement & question bank
├── postman/                 # API collection
│
├── .github/workflows/
│   ├── deploy.yml           # Production CI/CD (push to main)
│   └── preview.yml          # PR preview CI/CD
│
├── backend/
│   ├── pyproject.toml       # Python 3.11+, hatchling build
│   ├── Dockerfile           # Cloud Run container
│   ├── generate_data.py     # 250K transaction generator (seed=42)
│   ├── entrypoint.sh        # Container entrypoint (Litestream + uvicorn)
│   ├── litestream.yml       # Litestream replication config
│   │
│   └── src/insightxpert/
│       ├── main.py              # FastAPI app + async lifespan
│       ├── config.py            # Pydantic Settings (LLM, DB, limits)
│       ├── api/
│       │   ├── routes.py        # /chat (SSE), /sql, /train, /schema, /health, /feedback
│       │   └── models.py        # ChatRequest, ChatChunk, FeedbackRequest, etc.
│       ├── agents/
│       │   ├── analyst.py           # Core NL2SQL agent loop
│       │   ├── orchestrator.py      # Multi-agent coordinator
│       │   ├── orchestrator_planner.py  # Enrichment evaluation (4 categories)
│       │   ├── dag_executor.py      # Parallel task DAG
│       │   ├── response_generator.py    # Insight synthesizer + citation linker
│       │   ├── quant_analyst.py     # Statistical sub-agent
│       │   ├── stat_tools.py        # numpy/scipy/pandas tools
│       │   ├── tool_base.py         # Tool ABC, ToolContext, ToolRegistry
│       │   └── tools.py             # run_sql, get_schema, search_similar
│       ├── prompts/
│       │   ├── analyst_system.j2        # Analyst Jinja2 system prompt
│       │   └── statistician_system.j2   # Statistician Jinja2 system prompt
│       ├── llm/
│       │   ├── base.py          # LLMProvider protocol
│       │   ├── factory.py       # Registry-based provider factory
│       │   ├── gemini.py        # Google Gemini provider
│       │   └── ollama.py        # Ollama local provider
│       ├── db/
│       │   ├── connector.py     # SQLAlchemy wrapper (read-only guard, row limits)
│       │   └── schema.py        # DDL introspection
│       ├── rag/
│       │   ├── base.py          # VectorStoreBackend protocol
│       │   ├── store.py         # ChromaVectorStore: 4 collections
│       │   └── memory.py        # InMemoryVectorStore (for tests)
│       ├── auth/
│       │   ├── routes.py        # Login, logout, me, conversations CRUD
│       │   ├── models.py        # User, ConversationRecord, MessageRecord ORM
│       │   ├── security.py      # JWT + bcrypt
│       │   ├── dependencies.py  # get_current_user, get_db_session
│       │   ├── conversation_store.py  # Persistent CRUD
│       │   └── seed.py          # Admin user bootstrap
│       ├── admin/
│       │   ├── routes.py        # Org config CRUD, client-config endpoints
│       │   ├── config_store.py  # JSON config file management
│       │   └── models.py        # FeatureToggles, OrgConfig, OrgBranding
│       └── training/
│           ├── trainer.py       # RAG bootstrap (DDL + docs + 12 QA pairs)
│           ├── schema.py        # DDL constant (17-column transactions table)
│           ├── documentation.py # Business context & column descriptions
│           └── queries.py       # 12 example Q→SQL pairs (6 query types)
│
└── frontend/
    └── src/
        ├── app/             # Next.js App Router (layout, page, login, admin, automations)
        ├── components/
        │   ├── chat/        # ChatPanel, MessageBubble, MessageList, MessageInput, WelcomeScreen
        │   ├── chunks/      # ChunkRenderer, StatusChunk, SqlChunk, AnswerChunk, DataTable, ChartBlock
        │   ├── layout/      # AppShell, Header, UserMenu, LeftSidebar, RightSidebar
        │   ├── sidebar/     # ConversationList, ConversationItem, SearchResults, ProcessSteps
        │   ├── sql/         # SqlExecutor (direct SQL panel)
        │   ├── automations/ # WorkflowBuilder, DAG canvas, schedule picker, run history
        │   ├── insights/    # Insights bell, popover, modal drill-down
        │   ├── admin/       # FeatureToggles, BrandingEditor, UserOrgMappings, PromptEditor
        │   └── ui/          # Shadcn primitives
        ├── hooks/           # useSSEChat, useClientConfig, useTheme, useAutoScroll
        ├── lib/             # SSE client, chunk parser, chart detector, model utils
        ├── stores/          # Zustand stores (auth, chat, settings, client-config)
        └── types/           # TypeScript interfaces (ChatChunk, Message, AgentStep, Admin)
```

---

## Configuration

### Backend (`backend/.env.local`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `SECRET_KEY` | *(required)* | JWT signing secret |
| `LLM_PROVIDER` | `gemini` | `gemini` \| `ollama` \| `vertex` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `DATABASE_PATH` | `./insightxpert.db` | Transactions SQLite path |
| `AUTH_DATABASE_PATH` | `./insightxpert_auth.db` | Auth + conversations SQLite path |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB persistence directory |
| `MAX_ROWS` | `500` | Max rows returned per SQL query |
| `QUERY_TIMEOUT_SECONDS` | `30` | SQL execution timeout |
| `AGENTIC_MODE_ENABLED` | `true` | Enable multi-agent enrichment pipeline |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint (if `LLM_PROVIDER=ollama`) |
| `TURSO_URL` | *(empty)* | Turso sync URL — empty = pure local mode |

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL |

---

## Deployment

See **[DEPLOY.md](./DEPLOY.md)** for the full guide covering:

- Firebase Hosting setup with API rewrite to Cloud Run
- Cloud Run service configuration (memory, concurrency, secrets)
- GitHub Actions CI/CD with Workload Identity Federation (keyless GCP auth)
- Litestream GCS bucket configuration for SQLite replication
- PR preview environments

---

## Contributing / Extending

### Adding a New LLM Provider

1. Create `backend/src/insightxpert/llm/myprovider.py` implementing the `LLMProvider` protocol (`llm/base.py`).
2. Register a factory function in `llm/factory.py`:
   ```python
   _REGISTRY["myprovider"] = lambda settings: MyProvider(settings.my_api_key)
   ```
3. Set `LLM_PROVIDER=myprovider` in `.env.local`. No other files need to change.

### Adding a New Agent Tool

1. Subclass `Tool` from `agents/tool_base.py`:
   ```python
   class MyArgs(BaseModel):
       param: str = Field(description="...")

   class MyTool(Tool[MyArgs]):
       name = "my_tool"
       description = "Does something useful."

       def get_args_schema(self) -> Type[MyArgs]:
           return MyArgs

       async def execute(self, context: ToolContext, args: MyArgs) -> ToolResult:
           ...
   ```
2. Register in `agents/analyst.py`:
   ```python
   registry.register(MyTool())
   ```
3. The tool schema is automatically included in the next LLM call.

### Adding a New LLM Backend for Testing

Implement the `VectorStoreBackend` protocol (`rag/base.py`) or use the bundled `InMemoryVectorStore` for zero-dependency unit tests.

---

## Guardrails and Safety

| Guardrail | Implementation |
|-----------|---------------|
| Read-only SQL | Regex blocklist for DML/DDL keywords + SQLite `PRAGMA query_only` enforced at engine level |
| Row limits | `MAX_ROWS` cap applied to every query result |
| Query timeouts | `QUERY_TIMEOUT_SECONDS` enforced per execution |
| No hallucination | Force-tool-use: LLM cannot respond without at least one `run_sql` call |
| No causal claims | System prompt instructs correlation-only language; never implies causation |
| Fraud flag accuracy | `fraud_flag = 1` is clearly described as "flagged for review," not "confirmed fraud" |
| Error sanitisation | Stack traces and internal errors are never surfaced to the LLM or end user |
| No user profiling | The transactions dataset contains no `user_id`; no individual-level profiling is possible |
| Synthetic data caveats | Every insight includes a note that findings are directional (synthetic dataset) |

---

## Evaluation Criteria

| Criterion | Weight |
|-----------|--------|
| Insight Accuracy | 30% |
| Query Understanding | 25% |
| Explainability | 20% |
| Conversational Quality | 15% |
| Innovation and Technical Implementation | 10% |

---

## Team

| Member | Contribution |
|--------|-------------|
| **Nachiket Kandari** | System architecture, UI/UX, LLM pipeline (model selection, prompt engineering, query understanding, SQL generation, multi-agent orchestration, response synthesis, validation) |
| **Arush** | Data layer, SQL execution engine, API endpoints, deployment |

---

## Citing and Acknowledgements

If you found InsightXpert useful — for learning, as a reference architecture, or as a starting point — a mention or shoutout is appreciated but not required.

**Acknowledgements:**

- [Google Gemini](https://ai.google.dev/) — LLM backbone
- [ChromaDB](https://www.trychroma.com/) — Embedded vector store
- [FastAPI](https://fastapi.tiangolo.com/) — Async Python web framework
- [Next.js](https://nextjs.org/) / [Shadcn UI](https://ui.shadcn.com/) — Frontend framework and component library
- [Techfest IIT Bombay](https://techfest.org/) — Leadership Analytics Challenge that motivated this build

---

## License

MIT — see [LICENSE](./LICENSE).

Copyright (c) 2025 Nachiket Kandari.
