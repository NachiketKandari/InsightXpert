# Rules

- Never include "Generated with Claude Code" or similar attribution lines in PR descriptions, commit messages, or any generated content.

# InsightXpert

AI data analyst for the Techfest IIT Bombay Leadership Analytics Challenge.
Converts natural-language questions into SQL queries against 250K Indian UPI payment transactions using a custom multi-agent pipeline + Gemini + PostgreSQL.

## Project Structure

```
backend/
  src/insightxpert/
    main.py           # FastAPI entry point, lifespan startup/shutdown
    config.py         # Pydantic Settings (env vars / .env.local)
    agents/           # analyst, orchestrator, quant_analyst, clarifier, deep_think,
                      #   response_generator, dag_executor, stats_resolver, tools,
                      #   stat_tools, advanced_tools, common, tool_base
    api/              # SSE chat endpoint, request/response models
    auth/             # JWT auth, user/org models, conversation store, permissions
    admin/            # feature toggles, org branding, config store
    automations/      # service, scheduler (APScheduler), evaluator, nl_trigger, routes
    datasets/         # dataset service (CRUD, CSV upload, profiling), profiler, routes
    db/               # SQLAlchemy connector, data loader, schema, stats_computer, migrations
    insights/         # insights routes
    llm/              # LLMProvider protocol, Gemini/Ollama/VertexAI providers, factory
    memory/           # in-memory conversation store (LRU+TTL)
    prompts/          # Jinja2 templates (.j2) for all agent personas
    rag/              # ChromaDB vector store and VectorStoreBackend protocol
    storage/          # R2 file storage, PDF extraction, document service
    training/         # DDL, documentation, example queries, trainer bootstrap
    voice/            # Deepgram speech-to-text WebSocket proxy
  tests/
  pyproject.toml

frontend/
  src/
    app/              # Next.js 16 App Router pages (login, register, admin, automations)
    components/       # chat, chunks, dataset, admin, automations, insights, layout, sidebar, sql, ui
    hooks/            # use-sse-chat, use-voice-input, use-client-config, etc.
    lib/              # api client, sse-client, chart-detector, constants, utils
    stores/           # Zustand: auth, chat, settings, client-config, automation, insight, notification
    types/            # TypeScript type definitions
  package.json

docs/                 # Detailed documentation (architecture, api-reference, agent-pipeline, etc.)
```

## Running Locally

```bash
# Start local PostgreSQL
cd backend
docker compose up -d             # PostgreSQL on :5432

# Backend
python generate_data.py          # load 250K rows into PostgreSQL
uv run python -m insightxpert    # start FastAPI on :8000

# Frontend
cd frontend
npm install
npm run dev                      # Next.js dev server on :3000
```

## Key Config (backend/.env.local)

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google Gemini API key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model name |
| `LLM_PROVIDER` | `gemini` | `gemini`, `ollama`, or `vertex_ai` |
| `DATABASE_URL` | `postgresql://insightxpert:insightxpert@localhost:5432/insightxpert` | PostgreSQL connection URL |
| `CLOUD_SQL_CONNECTION_NAME` | `""` | Cloud SQL instance connection name (production) |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB persistence directory |
| `SECRET_KEY` | (insecure default) | JWT signing key (32+ chars for prod) |
| `DEEPGRAM_API_KEY` | `""` | Deepgram key for voice input (optional) |
| `LOG_LEVEL` | `INFO` | Logging level |

See `docs/configuration.md` for the full list of env vars.

## Architecture Overview

**Two-service deployment:** Firebase Hosting (Next.js static export) + Cloud Run (FastAPI backend) + Cloud SQL PostgreSQL.

**Agent pipeline modes** (`POST /api/chat`):
- `basic` — Single analyst loop: question -> SQL -> answer
- `agentic` — Analyst-first, then evaluator decides if enrichment is needed; DAG executes sub-tasks; synthesizer produces cited insight
- `deep` — 5W1H dimensional analysis with targeted enrichment

**Key subsystems:**
- **LLM layer** — `LLMProvider` protocol in `llm/base.py`; Gemini/Ollama/VertexAI providers; runtime model switching via `POST /api/config/switch`
- **RAG** — ChromaDB with 4 collections (qa_pairs, ddl, docs, findings); auto-save flywheel persists successful Q->SQL pairs
- **Tool system** — Custom `Tool` ABC in `agents/tool_base.py`; `ToolRegistry` dispatches tools; analyst tools (run_sql, get_schema, search_similar, clarify) + quant analyst tools (run_python, hypothesis tests, correlation, descriptive stats)
- **Auth** — JWT + HttpOnly `__session` cookie; dual-path (cookie for CDN-proxied routes, Bearer token for direct SSE)
- **SSE streaming** — `EventSourceResponse` yields `ChatChunk` objects; `[DONE]` sent before persistence (fire-and-forget)
- **Conversations** — Two-layer: in-memory LRU+TTL store for fast context injection; PostgreSQL for persistence
- **Datasets** — Multi-dataset support with CSV upload, automatic profiling, column metadata; active dataset's DDL/docs override training data
- **Automations** — APScheduler cron-based automation with trigger conditions (threshold, trend, etc.)

## Critical Patterns

### asyncio.to_thread for DB calls

The psycopg2 driver is synchronous C code. All DB calls in async handlers MUST be wrapped:

```python
# WRONG — blocks event loop
result = store.get_conversations(user_id)

# CORRECT
result = await asyncio.to_thread(store.get_conversations, user_id)
```

### Tool execute() returns JSON strings

Tool `execute()` must return `json.dumps(...)`. Errors are caught by `ToolRegistry` and returned as `{"error": str(e)}` — tracebacks never reach the LLM.

### Adding new tools

1. Create class in `agents/tools.py` (or `stat_tools.py`, `advanced_tools.py`) extending `Tool` from `agents/tool_base.py`
2. Implement `name`, `description`, `get_args_schema()` (returns JSON Schema dict), `execute(context, args)` (returns JSON string)
3. Register in `default_registry()` in `tools.py`

### Adding new LLM providers

1. Implement `LLMProvider` protocol from `llm/base.py` (just needs `model` property + `async chat()` method)
2. Register in `llm/factory.py`
3. Add config fields to `config.py` Settings class

### Tests

```bash
cd backend
uv run pytest tests/ -v
uv run pytest tests/ --cov=insightxpert --cov-report=term-missing
```

## Documentation

Detailed docs live in `docs/`:
- `architecture.md` — Full system architecture
- `agent-pipeline.md` — Agent processing pipeline (analyst loop, enrichment, DAG execution)
- `agent-tools.md` — All tool definitions and schemas
- `api-reference.md` — REST API endpoints
- `configuration.md` — All env vars and admin config
- `frontend.md` — Frontend stack, components, stores, hooks
- `contributing.md` — Repo layout, how to add tools/providers/collections, conventions
