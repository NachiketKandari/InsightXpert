# Contributing Guide

## Repository Layout

```
backend/
  src/insightxpert/
    agents/       # analyst, orchestrator, quant_analyst, clarifier, deep_think,
                  #   response_generator, dag_executor, stats_resolver, tools,
                  #   stat_tools, advanced_tools, common, tool_base
    api/          # FastAPI routes (SSE chat endpoint) and Pydantic request/response models
    auth/         # JWT auth, user/org models, conversation store, permissions, seed
    admin/        # feature toggles, org branding, config store, domain editor
    automations/  # service (CRUD), scheduler (APScheduler cron), evaluator (trigger logic),
                  #   nl_trigger (NL-to-trigger compiler), models (Pydantic schemas), routes
    benchmark/    # offline model benchmark runner, RAG isolation, report generation
    datasets/     # dataset service (CRUD, CSV upload, profiling), profiler (DataFrame column
                  #   stats/type inference), dependencies, routes
    db/           # SQLAlchemy connector, data loader, schema, stats_computer, migrations
    insights/     # insights routes
    llm/          # provider protocol (base.py), Gemini/Ollama/VertexAI implementations, factory
    memory/       # in-memory conversation store (wraps auth's PersistentConversationStore)
    prompts/      # Jinja2 prompt templates (.j2) for all agent personas
    rag/          # ChromaDB vector store (VectorStore) and protocol (VectorStoreBackend)
    storage/      # Cloudflare R2 file storage (r2.py), PDF text extraction (pdf_extractor.py),
                  #   document service (CRUD + LLM context), upload routes
    training/     # DDL, documentation, example queries, seed data, trainer bootstrap
    voice/        # Deepgram speech-to-text WebSocket proxy (browser audio -> Nova-3 -> transcript)
    config.py     # Pydantic Settings (all env vars)
    exceptions.py # Custom exception classes
    main.py       # FastAPI entry point
  tests/
  generate_data.py
  pyproject.toml

frontend/
  src/
    app/              # Next.js App Router pages
      admin/          #   Admin panel (users, feature toggles, automations, notifications)
      automations/    #   Automations page
      login/          #   Login page
      register/       #   Registration page
    components/
      admin/          # Admin UI: feature toggles, branding, domain editor, user mappings,
                      #   conversation viewer
      automations/    # Automation list, workflow builder/canvas, schedule picker, trigger
                      #   condition builder, AI SQL generator, run history
      chat/           # Chat panel, message input/list/bubble/actions, welcome screen
      chunks/         # Chunk renderers: answer, chart, clarification, data table, error,
                      #   insight, SQL, status, thinking trace, tool call/result, citation
      dataset/        # CSV upload dialog, PDF upload dialog, dataset viewer
      health/         # Health check gate
      insights/       # Insight bell, popover, cards, modal
      layout/         # App shell, header, left/right sidebars, user menu, dataset selector,
                      #   docs dialog
      notifications/  # Notification bell, popover, cards, list, detail modal
      sample-questions/ # Sample questions modal
      sidebar/        # Conversation list/item, process steps, search results
      sql/            # SQL executor, chart configurator
      ui/             # shadcn/ui primitives (button, input, dialog, sheet, tabs, etc.)
    hooks/            # use-auto-scroll, use-client-config, use-health-check, use-media-query,
                      #   use-sse-chat, use-syntax-theme, use-theme, use-voice-input
    lib/              # api, automation-utils, chart-detector, chunk-parser, constants,
                      #   export-report, file-utils, model-utils, sample-questions, sql-utils,
                      #   sse-client, utils
    stores/           # Zustand stores: auth, automation, chat, client-config, insight,
                      #   notification, settings
    types/            # TypeScript type definitions: admin, api, automation, chat, dataset, insight
  package.json
```

---

## Running Locally

### Backend

```bash
cd backend
python generate_data.py          # load 250K rows into insightxpert.db
uv run python -m insightxpert   # start FastAPI on :8000
```

Required env vars (`.env.local` in `backend/`):

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Model name (default: `gemini-2.5-flash`) |
| `LLM_PROVIDER` | Provider to use: `gemini`, `ollama`, or `vertex_ai` (default: `gemini`) |
| `DATABASE_URL` | SQLite path (default: `sqlite:///./insightxpert.db`) |
| `CHROMA_PERSIST_DIR` | ChromaDB data directory (default: `./chroma_data`) |
| `SECRET_KEY` | JWT signing secret (set a random 32+ char string for production) |
| `DEEPGRAM_API_KEY` | Deepgram API key for voice input (optional, leave empty to disable) |
| `OLLAMA_MODEL` | Ollama model name (default: `llama3.1`, used when `LLM_PROVIDER=ollama`) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `GCP_PROJECT_ID` | GCP project ID (required when `LLM_PROVIDER=vertex_ai`) |
| `VERTEX_AI_REGION` | Vertex AI region (default: `global`) |
| `VERTEX_AI_MODEL` | Vertex AI model name (default: `zai-org/glm-5-maas`) |
| `LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`) |

### Frontend

```bash
cd frontend
npm install
npm run dev    # Next.js dev server on :3000
```

---

## Adding a New LLM Provider

Providers live in `backend/src/insightxpert/llm/`. Each provider implements the `LLMProvider` protocol defined in `llm/base.py`. Current providers: Gemini (`gemini.py`), Ollama (`ollama.py`), Vertex AI (`vertex.py`).

### 1. Implement the protocol

Create `backend/src/insightxpert/llm/myprovider.py`:

```python
from __future__ import annotations
from insightxpert.llm.base import LLMProvider, LLMResponse, ToolCall

class MyProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        # Call the external API and return LLMResponse
        # LLMResponse fields: content, tool_calls, input_tokens, output_tokens
        ...
```

`LLMProvider` is a `@runtime_checkable Protocol` — no explicit inheritance required. The class just needs to have the right method signatures.

### 2. Register in the factory

`backend/src/insightxpert/llm/factory.py`:

```python
elif provider == "myprovider":
    from insightxpert.llm.myprovider import MyProvider
    return MyProvider(api_key=settings.my_api_key, model=settings.my_model)
```

Add an `else` branch or extend the `if/elif` chain. Raise `ValueError` for unknown providers.

### 3. Add config fields

`backend/src/insightxpert/config.py`:

```python
class Settings(BaseSettings):
    ...
    my_api_key: str = ""
    my_model: str = "my-model-default"
```

Also extend the `LLMProvider` enum:

```python
class LLMProvider(str, Enum):
    ...
    MY_PROVIDER = "myprovider"
```

### 4. Expose in the API

`backend/src/insightxpert/api/routes.py` builds the `ProviderModels` list returned by `GET /api/config`. Add your provider and models there so the frontend model-switcher can discover them.

---

## Adding a New Tool

Tools are defined in `backend/src/insightxpert/agents/tools.py` (core tools), `agents/stat_tools.py` (statistical tools for the quant analyst), or `agents/advanced_tools.py` (advanced analysis tools). All use the `Tool` base class from `agents/tool_base.py`.

### 1. Define the tool class

```python
from insightxpert.agents.tool_base import Tool, ToolContext, ToolRegistry
import json

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something useful. Describe when and how the LLM should call it."

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                }
            },
            "required": ["query"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        result = do_something(args["query"])
        return json.dumps({"result": result})
```

`execute()` must always return a JSON string. Errors are caught by `ToolRegistry.execute()` and returned as `{"error": "..."}` — never raise unhandled exceptions that would expose tracebacks to the LLM.

`ToolContext` provides:
- `context.db` — `DatabaseConnector` with an `execute(sql, row_limit)` method
- `context.rag` — `VectorStoreBackend` for RAG retrieval
- `context.row_limit` — configured SQL row limit
- `context.analyst_results` — list of dicts from the analyst's SQL result (for stat tools)
- `context.analyst_sql` — the SQL string that produced those results

### 2. Register the tool

In `default_registry()` in `tools.py`:

```python
def default_registry(...) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RunSqlTool())
    registry.register(GetSchemaTool())
    registry.register(SearchSimilarTool())
    registry.register(MyTool())          # add here
    if clarification_enabled:
        registry.register(ClarifyTool())
    return registry
```

For stat tools, add to `statistician_registry()` in `stat_tools.py`.

---

## Adding a New RAG Collection

The vector store has four collections: `qa_pairs`, `ddl`, `docs`, `findings`. The protocol is defined in `rag/base.py` (`VectorStoreBackend`) and the ChromaDB implementation is in `rag/store.py` (`VectorStore`).

To add a new collection:

### 1. Add to `VectorStore.__init__`

```python
self._my_collection = self._client.get_or_create_collection("my_collection")
```

### 2. Add `add_*` and `search_*` methods to `VectorStore`

Follow the pattern of existing methods (e.g. `add_finding`, `search_findings`). Use `self._doc_id(content)` for deduplication. Use `upsert` for idempotent writes.

### 3. Add to `VectorStoreBackend` protocol

`rag/base.py`:

```python
def add_my_document(self, content: str, metadata: dict | None = None) -> str: ...
def search_my_collection(self, question: str, n: int = 3) -> list[dict]: ...
```

### 4. Add to `InMemoryVectorStore`

For test compatibility, implement the same methods in the test fake used by `tests/conftest.py`.

### 5. Add to `delete_all()`

```python
def delete_all(self) -> dict[str, int]:
    ...
    n_my = len(self._my_collection.get()["ids"])
    self._my_collection.delete(where={"_id": {"$ne": ""}})
    return {..., "my_collection": n_my}
```

---

## Adding Training Data

Training data is bootstrapped on startup by `training/trainer.py`. On the first run it adds DDL, documentation, and example Q→SQL pairs to ChromaDB.

### At bootstrap (static)

Add to the respective files in `backend/src/insightxpert/training/` (see also `seed_data.py` for bootstrap seed data):

- **Q→SQL pairs**: add a dict to `EXAMPLE_QUERIES` in `queries.py`:
  ```python
  {
      "category": "Temporal",
      "question": "Which hour has the most failed transactions?",
      "sql": "SELECT hour_of_day, COUNT(*) AS failures FROM transactions WHERE transaction_status = 'FAILED' GROUP BY hour_of_day ORDER BY failures DESC LIMIT 1;",
  }
  ```
- **Documentation**: add a paragraph to the `DOCUMENTATION` string in `documentation.py`
- **DDL**: edit the `DDL` constant in `schema.py`

Changes are picked up on next startup. The trainer is idempotent — documents are SHA-256 keyed and use ChromaDB `upsert`, so re-running does not create duplicates.

### At runtime (via API)

```bash
# Add a Q→SQL pair
curl -X POST /api/train \
  -H "Content-Type: application/json" \
  -d '{"type": "qa_pair", "content": "How many transactions succeeded?", "metadata": {"sql": "SELECT COUNT(*) FROM transactions WHERE transaction_status = 'SUCCESS';"}}'

# Add documentation
curl -X POST /api/train \
  -d '{"type": "documentation", "content": "The fraud_flag column is 1 when a transaction was flagged for review..."}'

# Add DDL
curl -X POST /api/train \
  -d '{"type": "ddl", "content": "CREATE TABLE transactions (...)"}'
```

Requires admin authentication.

---

## Voice Input (Deepgram)

Voice input is implemented as a WebSocket proxy in `backend/src/insightxpert/voice/routes.py`. The browser records audio (WebM/opus), sends it over a WebSocket at `/api/transcribe`, and the backend proxies it to Deepgram Nova-3 for real-time transcription.

### Key files

- `backend/src/insightxpert/voice/routes.py` — WebSocket endpoint, authenticates via JWT (cookie or query param), proxies audio to Deepgram
- `frontend/src/hooks/use-voice-input.ts` — React hook for recording and receiving transcripts
- `backend/src/insightxpert/config.py` — `DEEPGRAM_API_KEY` setting (leave empty to disable)

### How it works

1. Browser opens a WebSocket to `/api/transcribe`
2. Backend authenticates via `__session` cookie or `?token=` query param
3. Backend opens a second WebSocket to `wss://api.deepgram.com/v1/listen`
4. Two concurrent tasks: `browser_to_deepgram` (audio) and `deepgram_to_browser` (transcripts)
5. Transcripts are streamed back as JSON with interim and final results

Voice is optional — if `DEEPGRAM_API_KEY` is empty the WebSocket closes with code `4002`.

---

## Document Storage (R2 + PDF)

File storage and PDF document management live in `backend/src/insightxpert/storage/`.

### Key files

- `storage/r2.py` — `R2StorageService`: Cloudflare R2 object storage via boto3 S3-compatible client (upload, delete, presigned URL generation). All methods are synchronous — callers must use `asyncio.to_thread()`.
- `storage/pdf_extractor.py` — `extract_text_from_pdf()`: extracts text from PDF files using `pypdf`, adds page markers, detects scanned PDFs without OCR.
- `storage/document_service.py` — `DocumentService`: CRUD for `Document` records (backed by SQLAlchemy), visibility rules (admins see all, users see own uploads + system docs), and `get_documents_context_markdown()` to inject extracted PDF text into LLM context.
- `storage/routes.py` — FastAPI routes at `/api/documents` for PDF upload, listing, and deletion. Max upload size is 20 MB.

### Adding a new file type

1. Add an extractor function in `storage/` (similar to `pdf_extractor.py`)
2. Update the validation in `storage/routes.py` to accept the new extension
3. Call the extractor in the upload handler and store extracted text in the `Document` record

---

## Automations

Automations allow users to schedule recurring SQL queries with trigger conditions and receive notifications. The module is in `backend/src/insightxpert/automations/`.

### Key files

- `automations/models.py` — Pydantic request/response schemas: `CreateAutomationRequest`, `TriggerCondition`, `AutomationResponse`, `NotificationResponse`, etc.
- `automations/service.py` — `AutomationService`: CRUD for automations, runs, notifications, and trigger templates. Uses normalized `automation_triggers` table with JSON blob fallback.
- `automations/scheduler.py` — `AutomationScheduler`: APScheduler-based cron scheduler that loads active automations, executes their SQL queries, and evaluates triggers.
- `automations/evaluator.py` — `TriggerEvaluator`: evaluates trigger conditions (threshold, row_count, change_detection, column_expression, slope) against query results.
- `automations/nl_trigger.py` — NL-to-trigger compiler: uses the LLM to convert plain English trigger descriptions into structured `TriggerCondition` JSON.
- `automations/routes.py` — FastAPI routes for automation CRUD, run history, trigger templates, notifications, and the NL trigger compiler.

### Trigger condition types

| Type | Description |
|---|---|
| `threshold` | Compare a single column value against a threshold |
| `row_count` | Compare the number of result rows |
| `change_detection` | Fire when a value changes by N% from the previous run |
| `column_expression` | Check a column value across rows (any_row / all_rows) |
| `slope` | Compute rate of change across recent runs |

### Frontend

- `frontend/src/components/automations/` — automation list, workflow builder (visual canvas), schedule picker, trigger condition builder, AI SQL generator, run history
- `frontend/src/stores/automation-store.ts` — Zustand store for automation state
- `frontend/src/types/automation.ts` — TypeScript types
- `frontend/src/app/automations/` — Automations page
- `frontend/src/app/admin/automations/` — Admin automations view

---

## Datasets

The datasets module handles multi-dataset management with CSV/PDF upload, column profiling, and example query management. Located in `backend/src/insightxpert/datasets/`.

### Key files

- `datasets/service.py` — `DatasetService`: CRUD for datasets, columns, and example queries. Handles CSV upload with automatic profiling via `profile_dataframe()`. Provides `get_active_dataset()` with a 60s TTL cache.
- `datasets/profiler.py` — `profile_dataframe()`: pure computational DataFrame profiler. Infers column types (INTEGER, REAL, TEXT, BOOLEAN, DATETIME), computes cardinality classification (unique/high/medium/low), null counts, numeric stats (min/max/mean), and sample values. Sanitizes column names for SQLite compatibility.
- `datasets/dependencies.py` — `resolve_user_roles`: dependency for resolving user roles (admin, org-scoped) in dataset routes.
- `datasets/routes.py` — FastAPI routes at `/api/datasets` for dataset CRUD, CSV upload, column management, and example queries.

### Frontend

- `frontend/src/components/dataset/csv-upload-dialog.tsx` — CSV file upload with preview
- `frontend/src/components/dataset/pdf-upload-dialog.tsx` — PDF document upload
- `frontend/src/components/dataset/dataset-viewer.tsx` — Dataset details and column browser
- `frontend/src/components/layout/dataset-selector.tsx` — Header dropdown to switch active dataset
- `frontend/src/types/dataset.ts` — TypeScript types

---

## Benchmark Runner

The offline benchmark suite in `backend/src/insightxpert/benchmark/` tests model accuracy across a question bank.

### Key files

- `benchmark/runner.py` — Core benchmark loop: iterates models and questions, collects chunk traces, measures timing
- `benchmark/rag_isolation.py` — Creates isolated RAG stores per benchmark run to avoid cross-contamination

Run with `python -m insightxpert.benchmark` from the `backend/` directory.

---

## Running Tests

```bash
cd backend
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_agent.py -v
uv run pytest tests/test_rag.py -v
uv run pytest tests/test_api_chat.py -v
uv run pytest tests/test_datasets.py -v
uv run pytest tests/test_orchestrator_integration.py -v
uv run pytest tests/test_statistician.py -v

# With coverage
uv run pytest tests/ --cov=insightxpert --cov-report=term-missing
```

Tests use `pytest-asyncio` (mode = `auto`). The `conftest.py` sets up an in-memory SQLite database and an `InMemoryVectorStore` so tests never touch the production database or ChromaDB.

Available test files: `test_agent`, `test_api_chat`, `test_admin_routes`, `test_clarifier`, `test_conversation_persistence`, `test_conversation_store_admin`, `test_data_loader`, `test_datasets`, `test_db`, `test_db_connector_dialect`, `test_error_scenarios`, `test_migrations`, `test_orchestrator_integration`, `test_prompts`, `test_statistician`, `test_validate_plan`.

Frontend end-to-end tests:

```bash
cd frontend
npm run test:e2e          # Playwright headless
npm run test:e2e:ui       # Playwright with UI
```

---

## Frontend Development

```bash
cd frontend
npm run dev       # Dev server on :3000
npm run build     # Production build
npm run lint      # ESLint
```

The dev server proxies `/api/*` to `http://localhost:8000` via Next.js rewrites (configured in `next.config.ts`).

---

## Code Style

### Backend

- **ruff** for linting and import sorting (configured in `pyproject.toml`)
- **mypy** for type checking
- All new endpoints must have a `response_model` on the FastAPI route decorator
- All new tools must have full type annotations
- All new async endpoint handlers that call synchronous DB/store methods must wrap those calls in `await asyncio.to_thread(store.method, args)`

### Frontend

- **ESLint** with the `eslint-config-next` ruleset
- **TypeScript strict mode** is on — no implicit `any`
- All new stores should follow the Zustand `create<StateType>()` pattern
- Prefer `useCallback` for event handlers passed to children to avoid unnecessary re-renders

---

## Project Conventions

### Backend

- All agent loops are `async def` functions that yield `ChatChunk` objects (via `AsyncGenerator[ChatChunk, None]`).
- All DB calls in `async def` handlers must use `await asyncio.to_thread(...)`. The SQLite driver is synchronous C code; calling it directly on the event loop will block all concurrent requests.
- Error messages returned to the LLM must not include Python tracebacks. `ToolRegistry.execute()` catches exceptions and returns `{"error": str(e)}` — keep error strings concise and actionable.
- New feature toggles go in `FeatureToggles` in `admin/models.py` and must be surfaced in the admin UI via `FeatureToggles` component.
- New services (like `AutomationService`, `DocumentService`, `DatasetService`) follow the same pattern: accept an SQLAlchemy `engine` in `__init__`, use `Session(self._engine)` context managers, and expose methods that return dicts (not ORM objects).
- All new SQLAlchemy models go in `auth/models.py`. Use `_uuid()` for primary keys and `_utcnow()` for timestamps.
- New API routers should be registered in `main.py` and follow the existing prefix convention (`/api/<module>`).
- Synchronous storage services (like `R2StorageService`) must be called via `asyncio.to_thread()` from async handlers.

### Frontend

- New chunk types must be added to `ChunkType` in `types/chat.ts` and handled in `chunks/chunk-renderer.tsx`.
- New stores should be non-persisted by default. Only persist state that must survive a page refresh (conversation list, agent mode). Use `sessionStorage` for ephemeral session state, `localStorage` for true persistence.
- All API calls go through `apiFetch` or `apiCall` in `lib/api.ts` — these attach credentials and base URL automatically.
- New page routes go in `app/` using the Next.js App Router convention (directory with `page.tsx` and optional `layout.tsx`).
- New TypeScript types go in `types/` — one file per domain (e.g., `automation.ts`, `dataset.ts`, `insight.ts`).
