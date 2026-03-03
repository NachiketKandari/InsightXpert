# InsightXpert Architecture

InsightXpert is an AI data analyst that converts natural-language questions into SQL queries against 250,000 Indian UPI payment transactions from 2024. This document covers the full system architecture — deployment topology, backend internals, storage, LLM integration, RAG pipeline, tool system, streaming, auth, admin, and frontend subsystems.

> **Visual diagram:** Open [`docs/diagrams/system-architecture.excalidraw`](diagrams/system-architecture.excalidraw) in [Excalidraw](https://excalidraw.com) for an interactive system architecture diagram covering the frontend, dual-path auth, backend services, agentic orchestrator, LLM layer, and database/storage topology.

---

## System Architecture

### Two-Service Deployment

Production runs as two independent services:

**Firebase Hosting** serves the Next.js static export (`frontend/out/`). The `firebase.json` configures two rewrite rules:

1. `GET /api/**` — rewrites to the Cloud Run service `insightxpert-api` in `us-central1`. This means the browser calls `/api/chat` but Firebase transparently proxies it to Cloud Run without CORS preflight issues.
2. `**` — falls through to `index.html` for client-side routing.

Static assets (JS, CSS, images, fonts) receive `Cache-Control: public, max-age=31536000, immutable` headers from Firebase Hosting for aggressive CDN caching.

**Cloud Run** runs the FastAPI backend container. The `Dockerfile` builds on `python:3.11-slim` and:
- Installs `uv` for fast dependency resolution from `pyproject.toml` / `uv.lock`
- Installs `litestream` for continuous SQLite replication to GCS
- Pre-downloads and warms the ChromaDB ONNX embedding model at build time to avoid cold-start timeouts
- Copies `upi_transactions_2024.csv` into the image so the transactions table can be loaded on first boot
- Exposes port `8080`

The `entrypoint.sh` implements startup logic:
- If `LITESTREAM_REPLICA_URL` is set: tries to restore the SQLite DB from a Litestream GCS replica; falls back to downloading a seed DB from GCS if no replica exists; then wraps uvicorn with `litestream replicate` for continuous replication
- If `LITESTREAM_REPLICA_URL` is unset: runs uvicorn directly (local dev or simple deployments)

### Local Development

In local dev, Next.js (`next dev` on port 3000) proxies `/api/**` to `http://localhost:8000` via `next.config.js` rewrites, matching the Firebase production topology exactly.

---

## Backend Architecture

### FastAPI Application

`backend/src/insightxpert/main.py` is the application entry point. It creates the FastAPI app with:
- `GZipMiddleware` (minimum_size=1000 bytes) for response compression
- `CORSMiddleware` configured from the `cors_origins` setting (comma-separated list)
- An `@asynccontextmanager` lifespan function that owns all startup and shutdown logic

Global exception handlers translate `InsightXpertError` subclasses, `RequestValidationError`, `HTTPException`, and unhandled `Exception` into consistent JSON error bodies with `error`, `detail`, and `status_code` fields. The generic handler manually attaches CORS headers because Starlette's `ServerErrorMiddleware` intercepts responses before `CORSMiddleware` can add them.

### Startup Sequence (lifespan)

The lifespan function performs these steps in order:

1. Connect `DatabaseConnector` to the SQLite database at `database_url`
2. Create all SQLAlchemy ORM tables (`AuthBase.metadata.create_all`)
3. Run `_migrate_schema()` — adds missing columns to existing tables idempotently (no Alembic)
4. Run `_migrate_trigger_conditions()` — normalizes legacy JSON trigger blobs into `automation_triggers` rows
5. Call `seed_admin()` — ensures the admin user exists (email/password from settings)
6. Backfill `conversations.org_id` from `users.org_id` for pre-org records
7. Seed `prompt_templates` table from `.j2` files (idempotent; updates stale templates that predate the clarification feature)
8. Seed `datasets`, `dataset_columns`, `example_queries` from hardcoded training data (idempotent)
9. `_ensure_transactions_loaded()` — loads `upi_transactions_2024.csv` into the `transactions` table if it is empty or missing
10. `compute_and_store_stats()` — pre-computes dataset statistics into `dataset_stats` table (idempotent)
11. Initialize `VectorStore` (ChromaDB)
12. Create LLM provider via `create_llm()`
13. Create `DatasetService`
14. Start RAG bootstrap as a background `asyncio.Task` (runs `Trainer.train_insightxpert()`)
15. Create `PersistentConversationStore` and `ConversationStore`
16. Store all services on `app.state`
17. Create `AutomationService` and `AutomationScheduler`, start the scheduler
18. Migrate legacy JSON admin config to the DB via `migrate_from_json()`
19. `await asyncio.wait_for(rag_task, timeout=rag_bootstrap_timeout_seconds)` — waits up to 120s for RAG bootstrap; server starts regardless

On shutdown: stops the automation scheduler, cancels the RAG task if still running, disposes the DB engine.

### Application State (`app.state`)

All services are attached to `app.state` during lifespan and accessed via `request.app.state` in route handlers:

| Attribute | Type | Purpose |
|---|---|---|
| `settings` | `Settings` | Pydantic config (env vars / .env.local) |
| `db` | `DatabaseConnector` | SQLAlchemy engine wrapper |
| `rag` | `VectorStore` | ChromaDB-backed vector store |
| `llm` | `LLMProvider` | Active LLM provider (swappable at runtime) |
| `auth_engine` | `Engine` | SQLAlchemy engine (same as `db.engine`) |
| `conversation_store` | `ConversationStore` | In-memory LRU+TTL conversation cache |
| `persistent_conv_store` | `PersistentConversationStore` | SQLite-backed conversation persistence |
| `dataset_service` | `DatasetService` | Dataset metadata and DDL resolution |
| `automation_service` | `AutomationService` | Automation CRUD |
| `automation_scheduler` | `AutomationScheduler` | Cron-based automation execution |

### Configuration (`Settings`)

`backend/src/insightxpert/config.py` — Pydantic `BaseSettings` loaded from environment variables and `.env.local`:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `ollama`, or `vertex_ai` |
| `GEMINI_API_KEY` | — | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model name |
| `OLLAMA_MODEL` | `llama3.1` | Ollama model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `GCP_PROJECT_ID` | — | GCP project for Vertex AI |
| `VERTEX_AI_REGION` | `global` | Vertex AI region |
| `VERTEX_AI_MODEL` | `zai-org/glm-5-maas` | Vertex AI model |
| `DATABASE_URL` | `sqlite:///./insightxpert.db` | SQLite database path |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB persistence directory |
| `MAX_AGENT_ITERATIONS` | `10` | Max analyst tool-call iterations |
| `MAX_QUANT_ANALYST_ITERATIONS` | `5` | Max quant analyst iterations |
| `MAX_ORCHESTRATOR_TASKS` | `5` | Max enrichment tasks per request |
| `SQL_ROW_LIMIT` | `10000` | Maximum rows returned per query |
| `SQL_TIMEOUT_SECONDS` | `30` | Query execution timeout |
| `PYTHON_EXEC_TIMEOUT_SECONDS` | `10` | Sandboxed Python execution timeout |
| `CORS_ORIGINS` | (see config) | Comma-separated allowed origins |
| `SECRET_KEY` | (insecure default) | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT TTL (24 hours) |
| `ADMIN_SEED_EMAIL` | `admin@insightxpert.ai` | Seeded admin email |
| `ADMIN_SEED_PASSWORD` | `admin123` | Seeded admin password |
| `RAG_BOOTSTRAP_TIMEOUT_SECONDS` | `120` | Max wait for RAG training at startup |
| `CONVERSATION_TTL_SECONDS` | `7200` | In-memory conversation TTL (2 hours) |
| `ENABLE_STATS_CONTEXT` | `true` | Global switch for stats context injection |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Database Layer

### Single SQLite File

Both the transactions table and all auth/operational tables share a single SQLite file (`insightxpert.db`). WAL journal mode is enabled on every connection via a `connect` event listener:

```python
def _enable_sqlite_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()
```

WAL mode allows concurrent readers alongside the single writer, which is important because the analyst agent reads the transactions table while background tasks may write to auth tables concurrently.

### DatabaseConnector

`backend/src/insightxpert/db/connector.py` — SQLAlchemy engine wrapper:

```python
class DatabaseConnector:
    def connect(self, url: str) -> None: ...
    def disconnect(self) -> None: ...
    def execute(self, sql: str, *, row_limit=1000, timeout=30, read_only=False) -> list[dict]: ...
    def get_tables(self) -> list[str]: ...
```

The `execute()` method:
- Opens a connection from the pool
- If `read_only=True` and dialect is SQLite: issues `PRAGMA query_only = ON` before the query
- Executes the SQL with `text()` (parameterized via SQLAlchemy)
- Fetches up to `row_limit` rows via `fetchmany()`
- Always resets `PRAGMA query_only = OFF` in a `finally` block so the connection is safe to return to the pool
- Returns `list[dict]` — each row is a dict of `{column_name: value}`

### Schema

Key tables in the single SQLite database:

**transactions** (250,000 rows, CSV-loaded)
- Core payment data: transaction_id, timestamp, amount, sender/receiver bank, state, merchant_category, device_type, network_type, payment_type, status, is_fraud, etc.
- Read-only at runtime; never written by the application

**users** — User accounts (id, email, hashed_password, is_active, is_admin, org_id, timestamps)

**organizations** — Per-org config with `features_json` and `branding_json` text blobs (JSON-serialized Pydantic models)

**app_settings** — Key-value store for global admin settings (admin_domains, defaults)

**conversations** — Conversation metadata (id, user_id, org_id, title, is_starred, timestamps)

**messages** — Per-message records (id, conversation_id, role, content, chunks_json, feedback, input_tokens, output_tokens, generation_time_ms, created_at)

**enrichment_traces** — Citation sources from agentic enrichment (message_id, source_index, category, question, final_sql, final_answer, trace_json)

**orchestrator_plans** — Saved enrichment plans (message_id, reasoning, plan_json, task_count)

**agent_executions** — Per-task execution records linked to plans (plan_id, message_id, task_id, agent_type, task_description, final_sql, final_answer, trace_json, duration_ms)

**prompt_templates** — Admin-editable system prompts (name, content, is_active)

**datasets** / **dataset_columns** / **example_queries** — Dataset registry with column metadata and example Q→SQL pairs

**automations** / **automation_runs** / **automation_triggers** — Automation workflow definitions and execution history

**dataset_stats** — Pre-computed statistics (stat_group, dimension, metric, value, string_value)

**insights** — Persisted agentic insights (user_id, org_id, conversation_id, message_id, title, summary, content, categories_json, enrichment_task_count)

### Migrations

`_migrate_schema()` in `main.py` handles schema evolution without Alembic. It iterates `MIGRATION_COLUMNS` (defined in `db/migrations.py`) — each entry is `(table, column, col_def)` — and issues `ALTER TABLE ... ADD COLUMN` idempotently by checking existing columns first. Index creation uses `CREATE INDEX IF NOT EXISTS`. Legacy tables (`feedback`, `alembic_version`) are dropped if present.

---

## LLM Layer

### LLMProvider Protocol

`backend/src/insightxpert/llm/base.py` defines a `@runtime_checkable Protocol`:

```python
class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    async def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse: ...
```

`LLMResponse` is a dataclass:

```python
@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
```

`ToolCall` carries `id`, `name`, and `arguments` (dict).

### Provider Factory

`create_llm(provider, settings)` in `llm/factory.py` is a simple string-dispatch factory:

```python
def create_llm(provider: str, settings: Settings) -> LLMProvider:
    if provider == "gemini":
        return GeminiProvider(api_key=..., model=...)
    elif provider == "ollama":
        return OllamaProvider(model=..., base_url=...)
    elif provider == "vertex_ai":
        return VertexAIProvider(project_id=..., region=..., model=...)
```

This avoids if/else chains in callers — the factory is the single registration point. Unsupported providers raise `ValueError`.

### Providers

- **GeminiProvider** (`llm/gemini.py`) — Uses the `google-generativeai` SDK. Default model: `gemini-2.5-flash`.
- **OllamaProvider** (`llm/ollama.py`) — Uses the `ollama` Python SDK with a 120-second timeout for slow local inference.
- **VertexAIProvider** (`llm/vertex.py`) — Uses Vertex AI Model Garden (GLM-5 and similar models).

### Token Counting Wrapper

`_TokenCountingLLM` in `api/routes.py` wraps any `LLMProvider` to accumulate token usage across the entire request:

```python
class _TokenCountingLLM:
    def __init__(self, llm) -> None:
        self._llm = llm
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    async def chat(self, messages, tools=None):
        resp = await self._llm.chat(messages, tools)
        self.input_tokens += resp.input_tokens
        self.output_tokens += resp.output_tokens
        return resp
```

Totals are emitted in the `metrics` SSE chunk at the end of each request and stored alongside the assistant message in the database.

### Runtime Model Switching

`POST /api/config/switch` accepts `{provider, model}` and replaces `app.state.llm` with a new provider instance. Previous settings are saved before the switch so they can be rolled back if `create_llm()` raises `ValueError`. For Ollama, the endpoint first verifies the model exists locally before switching.

---

## RAG Layer

### VectorStoreBackend Protocol

`backend/src/insightxpert/rag/base.py` defines a structural typing protocol:

```python
@runtime_checkable
class VectorStoreBackend(Protocol):
    def add_qa_pair(self, question, sql, metadata=None) -> str: ...
    def add_ddl(self, ddl, table_name="") -> str: ...
    def add_documentation(self, doc, metadata=None) -> str: ...
    def add_finding(self, finding, metadata=None) -> str: ...
    def search_qa(self, question, n=5, max_distance=None, sql_valid_only=False) -> list[dict]: ...
    def search_ddl(self, question, n=3) -> list[dict]: ...
    def search_docs(self, question, n=3) -> list[dict]: ...
    def search_findings(self, question, n=3) -> list[dict]: ...
    def flush_qa_pairs(self) -> int: ...
    def delete_all(self) -> dict[str, int]: ...
```

Any class implementing these methods satisfies the protocol — no explicit inheritance required. This makes test doubles trivial: an `InMemoryVectorStore` can implement the protocol with plain lists.

### ChromaDB Vector Store

`VectorStore` in `rag/store.py` backs four ChromaDB `PersistentClient` collections:

| Collection | Contents | Retrieval |
|---|---|---|
| `qa_pairs` | Question+SQL pairs (combined embedding: `"Question: ...\nSQL: ..."`) | `search_qa()` with optional `max_distance` and `sql_valid_only` filter |
| `ddl` | CREATE TABLE statements | `search_ddl()` |
| `docs` | Business documentation strings | `search_docs()` |
| `findings` | Anomaly findings (reserved; never populated) | `search_findings()` (always returns empty) |

**Deduplication**: every document ID is `SHA-256(content)[:16]`. Writes use ChromaDB's `upsert`, so inserting the same content twice is a no-op. The trainer is safe to call on every startup.

**Distance metric**: ChromaDB's default L2 (Euclidean) distance. Lower values = higher similarity. The analyst pipeline filters with `max_distance=1.0`.

**`search_qa()` parameters**:
- `n=5` — up to 5 results
- `max_distance=1.0` — discard weak matches
- `sql_valid_only=True` — only return pairs where `metadata.sql_valid == True`

### RAG Bootstrap (Trainer)

`training/trainer.py` `Trainer.train_insightxpert()` is called at startup in a background `asyncio.to_thread()`. It loads:
1. DDL from `training/schema.py` and live DB introspection via `get_schema_ddl(engine)`
2. Business documentation from `training/documentation.py`
3. Example Q→SQL pairs — first from the active dataset's `example_queries` table, then from `training/queries.py` as fallback

Approximately 12 seed Q→SQL pairs, the DDL, and the documentation are upserted. The trainer is idempotent due to content-hash IDs.

### Auto-Save (Self-Improving Flywheel)

After every successful analyst loop, `_extract_sql_from_messages()` walks the message list in reverse to find the last executed SQL (from a `run_sql` tool call or a fenced code block). The `(question, sql)` pair is persisted back to `qa_pairs` with `{"sql_valid": True}`. Over time, this means frequently asked questions accumulate accurate few-shot examples, improving future SQL generation without manual curation.

---

## Tool System

### Tool ABC

`backend/src/insightxpert/agents/tool_base.py`:

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def get_args_schema(self) -> dict: ...  # Returns JSON Schema dict

    @abstractmethod
    async def execute(self, context: ToolContext, args: dict) -> str: ...

    def get_definition(self) -> dict:
        """Build the JSON schema dict for LLM tool calling."""
        return {"name": self.name, "description": self.description, "parameters": self.get_args_schema()}
```

### ToolContext

```python
@dataclass
class ToolContext:
    db: DatabaseConnector
    rag: VectorStoreBackend
    row_limit: int = 1000
    analyst_results: list[dict] | None = None  # upstream rows for quant analyst
    analyst_sql: str | None = None             # upstream SQL for quant analyst
```

### ToolRegistry

Simple `dict[str, Tool]` with typed dispatch:

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def get_schemas(self) -> list[dict]: ...   # JSON schemas for LLM tool-calling
    async def execute(self, name, args, context) -> str: ...  # sanitized errors only
```

Unknown tool names return `{"error": "Unknown tool: ..."}` without raising. Exceptions inside `tool.execute()` are caught and returned as JSON error strings — tracebacks are never sent to the LLM or user.

### Built-In Analyst Tools

Registered by `default_registry()` in `agents/tools.py`:

**`RunSqlTool`** (`run_sql`) — Executes a SELECT query via `DatabaseConnector.execute()`. Supports optional `visualization`, `x_column`, `y_column` arguments that the frontend uses to render charts. Returns `{"rows": [...], "row_count": N}`.

**`GetSchemaTool`** (`get_schema`) — Returns DDL for specified tables or all tables via `get_schema_ddl(engine)`.

**`SearchSimilarTool`** (`search_similar`) — Searches `qa_pairs`, `ddl`, or `docs` collections in ChromaDB.

**`ClarifyTool`** (`clarify`) — Registered only when `clarification_enabled=True`. Returns `{"clarification": "...question..."}` which the analyst loop interprets as a stop signal, emitting a `clarification` chunk.

### Statistical Tools (Quant Analyst)

Defined in `agents/stat_tools.py` and registered by `_quant_registry()`:

- **`RunPythonTool`** (`run_python`) — Executes Python code in a restricted namespace. Pre-loaded: `np`, `pd`, `stats` (scipy.stats), `math`, `json`, `itertools`, `collections`, `functools`, `datetime`, `re`, `df` (analyst results as DataFrame). Import whitelist enforced via `_safe_import`. Timeout via `SIGALRM` (Unix only; silently disabled on Windows or non-main threads). Captured stdout returned as `{"output": "..."}`.
- **`ComputeDescriptiveStatsTool`** (`compute_descriptive_stats`) — count, mean, std, min, Q1, median, Q3, max, skewness, kurtosis via pandas/scipy.
- **`TestHypothesisTool`** (`test_hypothesis`) — chi_squared, t_test, mann_whitney, anova, z_proportion. Reports test statistic, p-value, effect size, and `significant_at_005` flag.
- **`ComputeCorrelationTool`** (`compute_correlation`) — Pearson, Spearman, or Kendall correlation between two columns.
- **`FitDistributionTool`** (`fit_distribution`) — Fits normal, exponential, lognormal, gamma, weibull_min distributions via KS test; ranks by p-value.
- **`RunSqlTool`** — also available in the quant analyst for additional data fetching.

---

## Prompt System

### Jinja2 Templates

Prompt templates live in `backend/src/insightxpert/prompts/` as `.j2` files:

- `analyst_system.j2` — Main system prompt for the SQL analyst. Conditional sections for `similar_qa` (RAG hits), DDL, documentation, `relevant_findings`, `stats_context`, and `clarification_enabled`.
- `statistician_system.j2` — System prompt for the statistician agent.
- `advanced_system.j2` — System prompt for the advanced analytics agent.
- `quant_analyst_system.j2` — System prompt for the quant analyst sub-agent.
- `orchestrator_planner.j2` — Prompt for task decomposition.
- `enrichment_evaluator.j2` — Prompt for the analyst-first enrichment evaluator.
- `response_generator.j2` — Prompt for synthesizing multiple evidence sources into a cited response.
- `deep_synthesizer.j2` — Prompt for the 5W1H Deep Think synthesis.

### Two-Tier Template Resolution

`prompts/__init__.py` `render(template_name, *, engine=None, **kwargs)`:

1. If `engine` is provided: query `prompt_templates` table for an active row matching `template_name` (without `.j2` suffix). DB-sourced templates are rendered in a `SandboxedEnvironment` to mitigate SSTI from admin-edited templates.
2. If no DB hit (or `engine=None`): load from the filesystem using a standard `Environment` with `FileSystemLoader`.

Both environments use `autoescape=False` (plain-text prompts, not HTML), `trim_blocks=True`, `lstrip_blocks=True`.

The `get_file_content()` function reads raw template bytes for the seed/reset admin endpoint, with a path-traversal guard that ensures the resolved path stays within the `prompts/` directory.

---

## SSE Streaming

### EventSourceResponse

`POST /api/chat` returns a `EventSourceResponse` (from `sse_starlette`). The async generator `event_generator()` yields `{"data": chunk_json}` dicts — each SSE event is a JSON-serialized `ChatChunk`.

### ChatChunk

```python
class ChatChunk(BaseModel):
    type: str          # chunk type (see below)
    data: dict | None  # type-specific structured data
    content: str | None
    sql: str | None
    tool_name: str | None
    args: dict | None
    conversation_id: str
    timestamp: float
```

Chunk types emitted during a request:

| Type | Source | Contents |
|---|---|---|
| `status` | analyst, orchestrator | Progress message string; optional `rag_context` titles or `agent`/`phase` data |
| `tool_call` | analyst | `tool_name`, `args`, optional `llm_reasoning` |
| `sql` | analyst | `sql` string for display |
| `tool_result` | analyst | `{"tool": name, "result": json_string}` |
| `stats_context` | analyst | Pre-computed stats markdown; `{"groups": [...]}` |
| `clarification` | analyst | Clarifying question text; `{"skip_allowed": true}` |
| `answer` | analyst | Final LLM text response |
| `orchestrator_plan` | orchestrator | `{"reasoning": ..., "tasks": [...]}` |
| `agent_trace` | orchestrator | Per-task execution details with `steps` |
| `enrichment_trace` | orchestrator | Citation source: source_index, category, question, sql, answer, steps |
| `insight` | orchestrator | Synthesized cited response (agentic mode only) |
| `error` | any | Error message string |
| `metrics` | api/routes.py | `{"input_tokens": N, "output_tokens": N, "generation_time_ms": N}` |

After the `metrics` chunk, the generator yields `{"data": "[DONE]"}` immediately. Persistence is fire-and-forget:

```python
asyncio.ensure_future(
    asyncio.to_thread(_persist_response, ...)
)
```

This ensures the client's spinner stops as soon as the answer is delivered, regardless of how long the DB write takes.

### Alternative Endpoints

- `POST /api/chat/poll` — Runs the full pipeline to completion and returns all chunks as a JSON array. Used by the automations scheduler.
- `POST /api/chat/answer` — Runs the full pipeline and returns only `{answer, conversation_id, sql}`. Used by benchmark runners.

---

## Auth System

### JWT + Cookies

`POST /api/auth/login` validates credentials, creates a JWT via `create_access_token()` (HS256, configurable expiry, default 24 hours), and sets it as an HTTP-only `__session` cookie.

The `get_current_user` FastAPI dependency:
1. Reads the `__session` cookie
2. Decodes the JWT with `decode_access_token(token, settings.secret_key)`
3. Loads the `User` ORM record from SQLite via `asyncio.to_thread(_fetch_user, engine, user_id)`
4. Checks `user.is_active`
5. Fire-and-forgets `_update_last_active()` as an `asyncio.create_task`
6. Returns the `User` object

Password hashing uses `bcrypt` (via the `bcrypt` package). `verify_password()` uses `checkpw` for constant-time comparison.

### Admin Access

`require_admin(user, admin_domains)` in `auth/dependencies.py` raises HTTP 403 if the user is not an admin. `is_admin_user()` in `auth/permissions.py` checks `user.is_admin` OR whether `user.email.split("@")[1]` matches any of the configured `admin_domains`.

Org-scoped admins see only conversations for users within their `org_id`. Admin-domain users bypass the org restriction.

---

## Admin System

### ClientConfig

`admin/models.py` defines the config data model:

```python
class FeatureToggles(BaseModel):
    sql_executor: bool = True
    model_switching: bool = True
    rag_training: bool = True
    chart_rendering: bool = True
    conversation_export: bool = True
    agent_process_sidebar: bool = True
    clarification_enabled: bool = True
    stats_context_injection: bool = False

class OrgBranding(BaseModel):
    display_name: str | None = None
    logo_url: str | None = None
    theme: dict[str, str] | None = None  # CSS variable overrides
    color_mode: str | None = None        # "dark" | "light" | None

class ClientConfig(BaseModel):
    admin_domains: list[str]
    user_org_mappings: list[UserOrgMapping]
    organizations: dict[str, OrgConfig]
    defaults: DefaultConfig
```

Config is stored in the DB: `organizations` table holds per-org `features_json` and `branding_json`; `app_settings` table holds `admin_domains` and `defaults` as JSON blobs.

### Feature Resolution

`_resolve_user_features(request, user)` in `api/routes.py`:
1. Load `ClientConfig` from DB (with 60s TTL cache via `_get_cached_config`)
2. Start from `config.defaults.features`
3. If user is not an admin AND their email domain is not in `admin_domains`: look up the user in `user_org_mappings`, find their org, override features with `org.features`
4. Return the resolved `FeatureToggles`

The 60-second TTL means admin config changes propagate to all users within one minute without requiring a server restart.

### Prompt Template Management

Admins can edit system prompts via the admin UI. Changes are stored in the `prompt_templates` table. The `render()` function checks the DB first on every call. DB-sourced templates are rendered in Jinja2's `SandboxedEnvironment` to prevent SSTI.

The seed endpoint loads the canonical on-disk `.j2` content back into the DB, allowing admins to reset a customized prompt to the factory default.

---

## Conversation System

### Two-Layer Architecture

**In-memory store** (`ConversationStore` in `memory/conversation_store.py`):
- `OrderedDict` keyed by conversation ID (LRU order)
- Max 500 conversations; LRU eviction when exceeded
- TTL-based expiry at access time (configurable, default 2 hours)
- Stores only condensed history: user messages + assistant final answers (no tool intermediaries)
- Returns last 20 turns (`MAX_HISTORY_TURNS`) for LLM context injection
- Used for fast in-request history lookups and context injection

**Persistent store** (`PersistentConversationStore` in `auth/conversation_store.py`):
- SQLite-backed via SQLAlchemy ORM
- Stores full message records with `chunks_json` (complete SSE event log), token counts, generation time, feedback
- Also stores `enrichment_traces`, `orchestrator_plans`, `agent_executions`, and `insights` linked to messages

### History Hydration

On cache miss (in-memory store has no history for a conversation ID), `_prepare_chat()` calls `persistent_store.get_conversation()` and replays the messages into the in-memory store:

```python
if not history and cid:
    convo_data = await asyncio.to_thread(persistent_store.get_conversation, cid, user.id)
    if convo_data and convo_data.get("messages"):
        for m in convo_data["messages"]:
            if m["role"] == "user":
                conv_store.add_user_message(cid, m["content"])
            elif m["role"] == "assistant":
                conv_store.add_assistant_message(cid, m["content"])
        history = conv_store.get_history(cid)
```

This handles server restarts and TTL expiry transparently — the LLM always gets conversation context.

---

## Dataset Service

`DatasetService` in `datasets/service.py` provides dataset metadata to the analyst and trainer:

- `get_active_dataset()` — Returns the currently active dataset (name, DDL, documentation) with a 60-second TTL cache
- `build_documentation_markdown(dataset_id)` — Builds a documentation string from `dataset_columns` records
- `list_datasets()`, `get_dataset_by_id()`, `activate_dataset()`, `create_dataset()`, `delete_dataset()` — Full CRUD

When an active dataset exists, the orchestrator uses its DDL and documentation instead of the hardcoded `training/schema.py` and `training/documentation.py` values. This allows users to upload custom CSV datasets and query them via natural language.

---

## Stats Context Injection

`StatsResolver` in `agents/stats_resolver.py` provides a fast path for simple metric questions:

1. `resolve(question, engine)` lowercases the question and matches against `STAT_PATTERNS` — a list of `(keywords, stat_groups)` tuples
2. If any keyword matches, fetches the corresponding `stat_group` rows from `dataset_stats`
3. Formats rows as compact markdown tables (single-dimension groups as key-value lists, multi-dimension groups as markdown tables)
4. Returns a `StatsResult(markdown, groups)` or `None` if no match

Example pattern:
```python
(["bank", "sbi", "hdfc", "icici", ...], ["bank"]),
(["fraud", "flag", "flagged", ...], ["overall", "merchant_category", "state"]),
```

The resolved markdown is injected into the system prompt under `## Pre-Computed Dataset Statistics`. If the LLM can answer directly from the stats, it skips SQL and emits a `stats_context` chunk. If it needs finer-grained data, it runs `run_sql` as normal.

This injection is gated by two flags: `config.enable_stats_context` (global) AND `features.stats_context_injection` (per-org admin toggle).

---

## Insights System

Insights are synthesized responses produced by the agentic orchestrator when enrichment tasks succeed. Each insight is persisted to the `insights` table with:
- `title` — the original user question
- `summary` — the evaluator's reasoning for why enrichment was needed
- `content` — the synthesized markdown response with citations
- `categories` — list of enrichment categories used (e.g. `["comparative_context", "temporal_trend"]`)
- `enrichment_task_count` — number of sub-tasks that contributed

The frontend's `InsightBell` component polls `/api/insights` for unread count, shows a popover with recent insights, and provides a "View All" modal.

---

## Automations System

### Backend

- **`AutomationService`** — CRUD for automations (name, description, NL query, SQL query, cron expression, trigger conditions, workflow JSON)
- **`AutomationScheduler`** — APScheduler-based cron scheduler. Polls due automations every minute, executes them via `POST /api/chat/poll`, evaluates trigger conditions against results, records `AutomationRun` rows
- **`AutomationTrigger`** — Normalized trigger conditions (type: threshold/trend/date_range, column, operator, value, change_percent, scope, slope_window)
- **`NLTrigger`** — Converts natural-language trigger descriptions to structured `AutomationTrigger` records via LLM
- **`AutomationEvaluator`** — Evaluates whether trigger conditions fired against a set of result rows

### Frontend

- `WorkflowBuilder` — react-flow canvas with `SqlBlockNode` nodes representing SQL query blocks
- `WorkflowCanvas` — Manages react-flow state, node positioning, edge connections
- `WorkflowSidebar` — Node property editor (SQL, visualization config)
- `TriggerConditionBuilder` — UI for building threshold/trend/date-range conditions with `ConditionRow` components
- `SchedulePicker` — Cron schedule builder (hourly, daily, weekly, custom)
- `AiSqlGenerator` — Natural language → SQL for automation queries via the chat API
- `RunHistory` / `RunDetailModal` — Automation run history with status, row counts, execution time, triggered conditions
- `AutomationList` / `AutomationCard` — CRUD list of all automations
- Automation store (Zustand) — persisted to `localStorage`

---

## Frontend Architecture

The Next.js frontend (`frontend/src/`) uses the App Router with TypeScript.

### Layout and Navigation

- `app/layout.tsx` — Root layout with providers (auth, theme)
- `components/layout/app-shell.tsx` — Three-column layout: left sidebar (conversation list), center (chat panel), right sidebar (agent process steps)
- `components/layout/header.tsx` — Model switcher, dataset selector, notification bell, insight bell, user menu
- `components/layout/left-sidebar.tsx` — Conversation list with search, star, rename, delete
- `components/layout/right-sidebar.tsx` — Live agent process steps during inference; enrichment traces after

### Chat

- `components/chat/chat-panel.tsx` — Orchestrates the chat UI; owns SSE connection via `sse-client.ts`
- `components/chat/message-list.tsx` — Virtualized message list; auto-scroll on new chunks
- `components/chat/message-bubble.tsx` — Per-message container; delegates chunk rendering
- `components/chat/message-input.tsx` — Textarea with submit; handles clarification "Just answer" path
- `components/chunks/chunk-renderer.tsx` — Dispatches `ChatChunk.type` to the correct chunk component

### Chunk Components

| Component | Chunk type |
|---|---|
| `status-chunk.tsx` | `status` |
| `tool-call-chunk.tsx` | `tool_call` |
| `sql-chunk.tsx` | `sql` |
| `tool-result-chunk.tsx` | `tool_result` |
| `answer-chunk.tsx` | `answer` (React.memo) |
| `insight-chunk.tsx` | `insight` |
| `stats-context-chunk.tsx` | `stats_context` |
| `clarification-chunk.tsx` | `clarification` |
| `error-chunk.tsx` | `error` |
| `thinking-trace.tsx` | `agent_trace` / `orchestrator_plan` |
| `trace-modal.tsx` | Expandable modal for enrichment trace steps |
| `citation-link.tsx` | Inline `[N]` citation that opens a trace modal |

### Stores

Zustand stores manage global client state:
- Auth store — JWT token, user info
- Notification store — Unread notifications (triggered by automation runs)
- Automation store — Persisted to `localStorage`

### API Client

`lib/api.ts` (or equivalent) — typed fetch wrappers for all backend endpoints. `sse-client.ts` implements the SSE consumer: reads chunked responses, parses `data:` lines, dispatches to a callback. React 18 batches state updates so the queue drains in a `while` loop without intermediate renders.
