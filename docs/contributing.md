# Contributing Guide

## Repository Layout

```
backend/
  src/insightxpert/
    agents/       # analyst, orchestrator, quant_analyst, clarifier, tools, stat_tools
    api/          # FastAPI routes and Pydantic request/response models
    auth/         # JWT auth, user models, conversation store
    admin/        # feature toggles, org branding, config store
    automations/  # scheduler, evaluator, nl_trigger
    datasets/     # dataset service and routes
    db/           # SQLAlchemy connector, data loader, schema, stats_computer
    insights/     # insights routes
    llm/          # provider protocol, Gemini/Ollama/VertexAI implementations, factory
    memory/       # in-memory conversation store (wraps auth's PersistentConversationStore)
    prompts/      # Jinja2 prompt templates
    rag/          # ChromaDB vector store (VectorStore) and protocol (VectorStoreBackend)
    training/     # DDL, documentation, example queries, trainer bootstrap
  tests/
  generate_data.py
  pyproject.toml

frontend/
  src/
    app/          # Next.js App Router pages
    components/   # All React components
    hooks/        # Custom hooks
    lib/          # Utilities (api, chart-detector, sse-client, sql-utils, etc.)
    stores/       # Zustand stores
    types/        # TypeScript type definitions
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
| `DATABASE_URL` | SQLite path (default: `sqlite:///./insightxpert.db`) |
| `CHROMA_PERSIST_DIR` | ChromaDB data directory (default: `./chroma_data`) |
| `SECRET_KEY` | JWT signing secret (set a random 32+ char string for production) |

### Frontend

```bash
cd frontend
npm install
npm run dev    # Next.js dev server on :3000
```

---

## Adding a New LLM Provider

Providers live in `backend/src/insightxpert/llm/`. Each provider implements the `LLMProvider` protocol defined in `llm/base.py`.

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

Tools are defined in `backend/src/insightxpert/agents/tools.py` (core tools) or `agents/stat_tools.py` (statistical tools for the quant analyst). Both files use the `Tool` base class from `agents/tool_base.py`.

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

Add to the respective files in `backend/src/insightxpert/training/`:

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

## Running Tests

```bash
cd backend
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_analyst.py -v
uv run pytest tests/test_rag.py -v
uv run pytest tests/test_api_chat.py -v

# With coverage
uv run pytest tests/ --cov=insightxpert --cov-report=term-missing
```

Tests use `pytest-asyncio` (mode = `auto`). The `conftest.py` sets up an in-memory SQLite database and an `InMemoryVectorStore` so tests never touch the production database or ChromaDB.

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

### Frontend

- New chunk types must be added to `ChunkType` in `types/chat.ts` and handled in `chunk-renderer.tsx`.
- New stores should be non-persisted by default. Only persist state that must survive a page refresh (conversation list, agent mode). Use `sessionStorage` for ephemeral session state, `localStorage` for true persistence.
- All API calls go through `apiFetch` or `apiCall` in `lib/api.ts` — these attach credentials and base URL automatically.
