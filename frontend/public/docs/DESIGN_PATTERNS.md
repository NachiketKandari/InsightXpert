# Design Patterns in InsightXpert

A comprehensive catalog of every design pattern used across the full stack, why each was chosen, and why it's a good fit for this project.

---

## Table of Contents

1. [Backend Architecture](#1-backend-architecture)
2. [Configuration & Environment](#2-configuration--environment)
3. [Database & Persistence](#3-database--persistence)
4. [Authentication & Authorization](#4-authentication--authorization)
5. [LLM Integration](#5-llm-integration)
6. [Agent & Tool System](#6-agent--tool-system)
7. [API Layer & Streaming](#7-api-layer--streaming)
8. [RAG & Vector Store](#8-rag--vector-store)
9. [Conversation Management](#9-conversation-management)
10. [Automations](#10-automations)
11. [Frontend State Management](#11-frontend-state-management)
12. [Frontend Component Patterns](#12-frontend-component-patterns)
13. [Frontend Performance](#13-frontend-performance)
14. [Infrastructure & Deployment](#14-infrastructure--deployment)
15. [Error Handling](#15-error-handling)
16. [Observability](#16-observability)

---

## 1. Backend Architecture

### 1.1 Async Context Manager Lifespan

**Files:** `backend/src/insightxpert/main.py:357-517`

**Pattern:** FastAPI's `@asynccontextmanager` with `async def lifespan(app)` manages the entire application lifecycle — startup resources before `yield`, cleanup after.

**Implementation:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB → migrations → sync → RAG → LLM → scheduler
    yield
    # Shutdown: close connections, stop scheduler
```

**Why it's used:** The app has ~8 interdependent resources (DB engines, sync managers, RAG store, LLM, scheduler) that must initialize in order and clean up on shutdown.

**Why it's good:** Guarantees resource cleanup even on crashes. Sequential initialization with per-stage error handling means a RAG timeout doesn't prevent the server from starting — it degrades gracefully. The alternative (scattered `@app.on_event` handlers) doesn't compose well and was deprecated by FastAPI.

---

### 1.2 Lazy Initialization with Background Tasks

**Files:** `backend/src/insightxpert/main.py:440-483`

**Pattern:** RAG bootstrap runs as `asyncio.create_task()` with a timeout, so the server becomes ready before training completes.

**Why it's used:** RAG training reads DDL, documentation, and example queries into ChromaDB — this can take 10-30s on cold start.

**Why it's good:** The server starts accepting HTTP requests immediately. If RAG training times out (configurable via `RAG_BOOTSTRAP_TIMEOUT_SECONDS`), the server warns but doesn't crash. Users get degraded (less-accurate) results rather than a 503.

---

### 1.3 Middleware Stack (CORS + GZip)

**Files:** `backend/src/insightxpert/main.py:523-530`

**Pattern:** Cross-cutting concerns handled as middleware layers — CORS for cross-origin browser requests, GZip for response compression.

**Why it's used:** The frontend (Firebase Hosting) and backend (Cloud Run) are on different domains. Chat responses can be large (10K+ row results).

**Why it's good:** Centralized, declarative, and invisible to route handlers. Every response gets compressed and CORS-compliant headers without any per-route code.

---

## 2. Configuration & Environment

### 2.1 Pydantic Settings with Validators

**Files:** `backend/src/insightxpert/config.py`

**Pattern:** `Settings(BaseSettings)` loads from `.env.local`, with field validators (normalize empty strings, validate log levels) and model validators (warn on insecure defaults).

**Why it's used:** The app has ~30 config variables across LLM providers, databases, auth, and agent behavior.

**Why it's good:**
- **Type safety:** Every config value is typed and validated before the server starts. A typo in `LOG_LEVEL` fails fast at boot, not at the first log call.
- **Single source of truth:** All env vars documented in one file with defaults.
- **Security checks:** Model validators warn if `SECRET_KEY` is too short or `ADMIN_SEED_PASSWORD` is weak — catches insecure deployments early.

---

### 2.2 Feature Toggles (JSON in DB)

**Files:** `backend/src/insightxpert/auth/models.py:46-63`, `backend/src/insightxpert/admin/models.py`

**Pattern:** `FeatureToggles` and `OrgBranding` are Pydantic models stored as JSON blobs in the `app_settings` table. Per-organization overrides layer on top of global defaults.

**Why it's used:** Different organizations may need different features (SQL executor, clarification, agent modes) without schema migrations.

**Why it's good:** Adding a new feature toggle is a one-line Pydantic field addition — no `ALTER TABLE`, no migration file. The `_resolve_user_features()` function applies a clean layering: global defaults → org overrides → hardcoded gates.

---

### 2.3 TTL Config Cache

**Files:** `backend/src/insightxpert/api/routes.py:60-75`

**Pattern:** Admin config cached in-memory with a 60-second TTL. On cache miss, reads from DB and stores `(timestamp, config)` tuple.

```python
_config_cache: dict[str, tuple[float, ClientConfig]] = {}
_CONFIG_TTL = 60.0
```

**Why it's used:** Every chat request needs the admin config to resolve feature flags. Without caching, that's a DB read per message.

**Why it's good:** Eliminates ~99% of config DB queries. 60s TTL means config changes propagate within a minute. No cache invalidation complexity — time-based expiry is simple and predictable.

---

## 3. Database & Persistence

### 3.1 Database Adapter/Wrapper

**Files:** `backend/src/insightxpert/db/connector.py`

**Pattern:** `DatabaseConnector` wraps a SQLAlchemy engine with dialect-aware logic — URL normalization, connection pool strategy, read-only pragmas, and timeout handling.

**Why it's used:** The app supports both local SQLite and remote Turso (libSQL over HTTPS). Each has different pooling needs, URL schemes, and failure modes.

**Why it's good:** Route handlers and tools call `db.execute(sql)` without knowing whether they're hitting a local file or a remote HTTP endpoint. The connector handles:
- URL scheme translation (`libsql://` → `sqlite+libsql://`)
- Pool strategy (connection pool for local, `NullPool` for remote)
- SQLite-specific pragmas (WAL mode, foreign keys)

---

### 3.2 Dialect-Aware Connection Pooling

**Files:** `backend/src/insightxpert/db/connector.py:67-72`

**Pattern:**
- **Local SQLite:** `pool_size=5, max_overflow=10, pool_pre_ping=True`
- **Remote Turso:** `NullPool` (fresh HTTP connection per request)

**Why it's used:** The libSQL driver raises `ValueError` (not a DBAPI error) when a pooled Turso connection's stream expires server-side. SQLAlchemy's pool health checks can't catch non-DBAPI errors.

**Why it's good:** Prevents the "stream not found" 500 errors that plagued early versions. Local SQLite gets efficient connection reuse; Turso gets the only strategy that works reliably with its HTTP-based protocol.

---

### 3.3 Async-to-Sync Bridging (`asyncio.to_thread`)

**Files:** `auth/dependencies.py:69,76`, `auth/routes.py:46`, `api/routes.py:147`, and ~20 more endpoints

**Pattern:** Every synchronous SQLite/SQLAlchemy call is wrapped in `await asyncio.to_thread(sync_func, ...)`.

**Why it's used:** FastAPI runs on an async event loop. SQLite's C driver is synchronous — a 50ms query blocks the entire event loop, freezing all concurrent requests.

**Why it's good:** Moves blocking I/O to a thread pool worker, keeping the event loop free for other requests. The pattern is explicit and auditable — every DB call site is visibly wrapped. The alternative (using an async DB driver) isn't available for SQLite/libSQL.

---

### 3.4 Bidirectional Background Sync

**Files:** `backend/src/insightxpert/db/sync.py`

**Pattern:** `TursoSyncManager` implements three-phase sync:
1. **Startup pull:** Bulk-load Turso → local SQLite (hydrate auth tables)
2. **Background push:** Every 30s, push changed rows local → Turso (timestamp-based change detection)
3. **Delete propagation:** `_sync_deletes` table tracks deletions for async push

**Why it's used:** The app needs sub-millisecond query latency (local SQLite) with durable cloud backup (Turso).

**Why it's good:**
- **Column intersection sync:** Only pushes columns that exist in both DBs, handling schema drift gracefully
- **FK-safe insertion order:** Tables synced in dependency order (parents before children)
- **Idempotent:** Re-running sync produces the same result — safe for crash recovery
- **Optional:** If `TURSO_URL` is empty, the app runs in pure local mode with zero sync overhead

---

### 3.5 Idempotent Schema Migrations

**Files:** `backend/src/insightxpert/main.py:36-113`

**Pattern:** `_migrate_schema()` checks column existence before `ALTER TABLE ADD COLUMN`. Indexes use `CREATE INDEX IF NOT EXISTS`. Runs on every startup.

**Why it's used:** The app evolves its schema frequently (new columns for features, stats, automations) without a traditional migration tool like Alembic.

**Why it's good:** Zero migration state to track. Safe to run 1000 times. A new column is a one-line addition to `_MIGRATION_COLUMNS` — shared between local migrations and Turso sync. The tradeoff (no down-migrations) is acceptable for a startup-stage product.

---

### 3.6 Delete Tracking via Logging Table

**Files:** `backend/src/insightxpert/auth/models.py:28-43`

**Pattern:** `_record_delete()` writes to `_sync_deletes` table instead of relying on the absence of rows.

**Why it's used:** Background sync can't detect deletions by comparing snapshots — a missing row could mean "deleted" or "not yet synced."

**Why it's good:** Explicit delete records enable reliable propagation to Turso. Provides an audit trail. Allows recovery if sync fails mid-flight.

---

### 3.7 SQLite Pragmas for Safety

**Files:** `backend/src/insightxpert/db/connector.py:13-18, 103-123`

**Pattern:** Every new connection runs:
- `PRAGMA foreign_keys = ON` (enforce referential integrity)
- `PRAGMA journal_mode = WAL` (concurrent reads during writes)
- `PRAGMA query_only = ON` (for analytics queries — prevents accidental writes)

**Why it's used:** SQLite defaults are permissive — foreign keys are off, journal mode is DELETE (locks entire DB on writes).

**Why it's good:** WAL mode enables the chat API to read while the sync manager writes. Read-only pragma on analytics queries provides defense-in-depth against SQL injection or LLM-generated DML.

---

## 4. Authentication & Authorization

### 4.1 JWT in HttpOnly Cookies

**Files:** `backend/src/insightxpert/auth/security.py`, `auth/routes.py:20-27,61-70`, `auth/dependencies.py:45-77`

**Pattern:** HS256-signed JWT stored in `__session` HttpOnly cookie. Token contains `{sub: user_id, email, exp}`.

**Why it's used:** The SPA frontend needs stateless auth that works across page reloads without client-side token management.

**Why it's good:**
- **HttpOnly:** JavaScript can't access the token — prevents XSS-based token theft
- **Stateless:** No server-side session store needed
- **Auto-sent:** Browser includes cookies automatically — no manual `Authorization` header in fetch calls
- **Cross-site aware:** `_cookie_flags()` detects HTTPS and cross-origin requests, sets `SameSite=None` only when needed

---

### 4.2 Bcrypt Password Hashing

**Files:** `backend/src/insightxpert/auth/security.py:11-16`

**Pattern:** `hash_password()` uses bcrypt with auto-generated salt. `verify_password()` uses bcrypt's constant-time comparison.

**Why it's used:** Passwords must be stored irreversibly with resistance to rainbow tables and timing attacks.

**Why it's good:** Bcrypt is intentionally slow (adaptive cost factor), making brute-force attacks impractical. Constant-time comparison prevents timing side-channels. The auto-salt means no developer can forget to salt a password.

---

### 4.3 FastAPI Dependency Injection for Auth

**Files:** `backend/src/insightxpert/auth/dependencies.py`

**Pattern:** `get_current_user()` is an async FastAPI dependency that extracts the JWT from cookies, decodes it, fetches the user from DB, and fire-and-forgets a `last_active` timestamp update.

**Why it's used:** Every protected endpoint needs the current user. Dependency injection lets routes declare `user = Depends(get_current_user)` and get a fully-resolved `User` object.

**Why it's good:**
- **Single responsibility:** Auth logic in one place, not scattered across 30 endpoints
- **Testable:** Can override the dependency in tests with a mock user
- **Composable:** `_get_admin_context()` builds on `get_current_user()` to add admin-specific context

---

### 4.4 Domain-Based Admin Detection

**Files:** `backend/src/insightxpert/auth/permissions.py`

**Pattern:** `is_admin_user()` checks two things: the explicit `user.is_admin` flag, and whether the user's email domain is in the `admin_domains` config list.

**Why it's used:** Auto-promoting all `@insightxpert.ai` users as admin without per-user DB entries.

**Why it's good:** New team members get admin access automatically. No manual user management for the core team. The explicit `is_admin` flag still exists for granting admin to external users.

---

### 4.5 Multi-Level Admin Scope

**Files:** `backend/src/insightxpert/admin/routes.py:43-76`

**Pattern:** Two admin tiers:
- **Super-admin:** `user.org_id = NULL` → sees all users and conversations
- **Org-scoped admin:** `user.org_id = "org_123"` → sees only users in their org

**Why it's used:** The platform serves multiple organizations. Org admins should manage their own users without seeing others.

**Why it's good:** Scope checking happens once in `_get_admin_context()`, then all admin endpoints use `_assert_user_in_scope()` and `_assert_conversation_in_scope()`. Adding a new admin endpoint gets scope checks for free.

---

## 5. LLM Integration

### 5.1 Protocol-Based Provider Abstraction

**Files:** `backend/src/insightxpert/llm/base.py:34-41`

**Pattern:** `@runtime_checkable` Protocol defines `LLMProvider`:
```python
class LLMProvider(Protocol):
    model: str
    async def chat(self, messages, tools=None) -> LLMResponse: ...
```

**Why it's used:** The app supports Gemini and Ollama, with potential for more providers.

**Why it's good:** Python Protocols enable structural (duck) typing — any class with a `model` property and `chat()` method satisfies the interface, no inheritance required. This is more Pythonic than abstract base classes and allows third-party classes to conform without modification.

---

### 5.2 Factory Pattern with Lazy Imports

**Files:** `backend/src/insightxpert/llm/factory.py`

**Pattern:** `create_llm(provider, settings)` uses conditional imports inside branches:
```python
if provider == "gemini":
    from insightxpert.llm.gemini import GeminiProvider
    return GeminiProvider(...)
```

**Why it's used:** Gemini and Ollama have different SDK dependencies. Importing both at module level wastes memory and may fail if one SDK isn't installed.

**Why it's good:** Lazy imports mean only the selected provider's SDK is loaded. Adding a new provider is a new `elif` branch + a new module. The factory is the single point of provider construction — no provider-specific code leaks into the rest of the app.

---

### 5.3 Message Format Translation

**Files:** `backend/src/insightxpert/llm/gemini.py`

**Pattern:** `GeminiProvider._convert_messages()` and `_convert_tools()` translate between an internal OpenAI-like format and Gemini's native format.

**Why it's used:** The agent system uses a single internal message format. Each LLM provider has its own wire format (Gemini uses `Content(role="model")`, `FunctionDeclaration`, etc.).

**Why it's good:** The entire agent/tool/orchestrator stack is provider-agnostic. Switching from Gemini to Ollama doesn't change a single line outside the LLM layer. Translation logic is co-located with the provider implementation.

---

### 5.4 Token Counting Wrapper

**Files:** `backend/src/insightxpert/api/routes.py:78-94`

**Pattern:** `_TokenCountingLLM` wraps any `LLMProvider`, intercepting `chat()` responses to accumulate `input_tokens` and `output_tokens`.

**Why it's used:** Token usage needs to be tracked per-chat-request for metrics, without modifying provider implementations.

**Why it's good:** Classic Decorator pattern — transparent to the caller, works with any provider, accumulates across multi-turn tool loops. The wrapper is created per-request, so there's no shared mutable state.

---

## 6. Agent & Tool System

### 6.1 Abstract Tool + Registry

**Files:** `backend/src/insightxpert/agents/tool_base.py`

**Pattern:** Abstract `Tool` base class with `name`, `description`, `get_args_schema()`, `execute()`. `ToolRegistry` stores tools by name, generates LLM-compatible schemas, and dispatches execution.

**Why it's used:** The LLM needs a standardized way to discover and call tools (run_sql, visualize, etc.).

**Why it's good:**
- **Self-documenting:** `get_definition()` auto-generates the JSON schema the LLM needs for function calling
- **Pluggable:** Register a new tool with `registry.register(MyTool())` — no changes elsewhere
- **Error-safe:** `ToolRegistry.execute()` catches exceptions and returns error strings to the LLM instead of crashing

---

### 6.2 Tool Context Dataclass

**Files:** `backend/src/insightxpert/agents/tool_base.py:17-23`

**Pattern:** `@dataclass ToolContext` bundles dependencies (DB connector, RAG store) and execution state (row limit, prior results, prior SQL).

**Why it's used:** Tools need access to shared resources without global state or passing 6 parameters to every `execute()` call.

**Why it's good:** Type-safe, explicit, immutable after construction. The context is created per-request and passed through the tool chain — no hidden coupling. Adding a new dependency is a new field, not a signature change across all tools.

---

### 6.3 Shared Agent Tool Loop

**Files:** `backend/src/insightxpert/agents/common.py:32-130`

**Pattern:** `agent_tool_loop()` is an async generator implementing the standard agentic loop: call LLM → if tool calls, execute and append results → repeat until text response or max iterations.

**Why it's used:** Both the analyst agent and statistician agent follow the same loop structure. Without this, each agent would duplicate ~100 lines of loop logic.

**Why it's good:** DRY — the loop, error handling, and chunk yielding are written once. Each agent just provides its system prompt and tool set. The generator pattern (`async for chunk in agent_tool_loop(...)`) integrates naturally with SSE streaming.

---

### 6.4 Multi-Phase Orchestrator

**Files:** `backend/src/insightxpert/agents/orchestrator.py:44-195`

**Pattern:** `orchestrator_loop()` orchestrates a pipeline:
- **Phase 0:** Optional clarification check
- **Phase 1:** Analyst agent (always runs, generates SQL and results)
- **Phase 2:** Conditional downstream agent (statistician or advanced) that receives Phase 1's SQL and results

**Why it's used:** Complex analytics often need two stages — first get the data (analyst), then analyze it (statistician).

**Why it's good:** Mode-driven routing (`"analyst"`, `"auto"`, `"statistician"`, `"advanced"`) lets the same orchestrator handle simple and complex queries. Phase 1 results are captured via chunk interception (not re-executed), so the downstream agent gets concrete data without a second DB query.

---

### 6.5 Result Capture via Chunk Interception

**Files:** `backend/src/insightxpert/agents/orchestrator.py:131-155`

**Pattern:** While consuming analyst chunks for SSE output, the orchestrator intercepts `type=="sql"` and `type=="tool_result"` chunks to capture the last SQL statement and result rows.

**Why it's used:** The downstream agent needs the analyst's results without re-running the query.

**Why it's good:** Zero-copy — the results flow through the SSE stream to the client AND get captured for the next phase. No intermediate storage or re-execution needed.

---

## 7. API Layer & Streaming

### 7.1 Server-Sent Events (SSE)

**Files:** `backend/src/insightxpert/api/routes.py` (chat_sse endpoint)

**Pattern:** `EventSourceResponse` from `sse-starlette` wraps an async generator that yields `ChatChunk` objects as SSE events. Terminal signal is `data: [DONE]`.

**Why it's used:** Chat responses are multi-second operations with multiple phases (SQL generation → execution → visualization → summary). Users need real-time feedback.

**Why it's good:** SSE is simpler than WebSockets for server-to-client streaming — no connection upgrade, no bidirectional state management. Works through proxies and load balancers. The `[DONE]` sentinel enables clean client-side stream termination.

---

### 7.2 Fire-and-Forget Persistence

**Files:** `backend/src/insightxpert/api/routes.py:273-285`

**Pattern:** After yielding `[DONE]` to the client, persistence runs as `asyncio.ensure_future(asyncio.to_thread(_persist_response, ...))`.

**Why it's used:** Persisting large responses (with chunk blobs) to Turso via HTTPS could take 15-20 seconds. This was the root cause of the 37s vs 17s latency gap.

**Why it's good:** The client sees `[DONE]` immediately after the last chunk. Persistence happens in the background. If it fails, the conversation is still in memory — the next request can retry.

---

### 7.3 Feature Resolution with Layered Overrides

**Files:** `backend/src/insightxpert/api/routes.py:97-116`

**Pattern:** `_resolve_user_features()` applies three layers:
1. Global defaults from admin config
2. Org-specific overrides (if user has org_id and is not admin)
3. Hardcoded gates (e.g., `clarification_enabled = False`)

**Why it's used:** Different organizations need different features, but some features need a kill switch regardless of config.

**Why it's good:** Clean separation of config sources. The layering order is explicit and predictable. Hardcoded gates serve as circuit breakers for features that aren't production-ready.

---

### 7.4 SQL Query Validation (Regex Allowlist)

**Files:** `backend/src/insightxpert/api/routes.py:527-544`

**Pattern:** `_FORBIDDEN_SQL` regex matches DML/DDL keywords (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE). The SQL executor endpoint rejects matches with HTTP 403.

**Why it's used:** The SQL executor lets users run arbitrary queries against the analytics DB. Write operations must be blocked.

**Why it's good:** Simple, fast, and auditable. Combined with SQLite's `PRAGMA query_only = ON` at the connection level, this provides defense-in-depth. The regex catches obvious DML; the pragma catches anything the regex misses.

---

### 7.5 Response Payload Truncation

**Files:** `backend/src/insightxpert/api/routes.py:607-631`

**Pattern:** `_truncate_chunks()` limits historical result sets to 50 rows, setting `truncated=True` and `original_row_count` for transparency.

**Why it's used:** Conversation history can include 10K+ row results. Loading full results for every historical message wastes bandwidth and memory.

**Why it's good:** Keeps history payloads small while preserving metadata about the original result size. The client can indicate truncation in the UI.

---

## 8. RAG & Vector Store

### 8.1 Content-Addressable Deduplication

**Files:** `backend/src/insightxpert/rag/store.py:61-76`

**Pattern:** `VectorStore._make_id()` derives a deterministic ID from `SHA-256(content)[:16]`. All writes use ChromaDB's `upsert()` keyed by this hash.

**Why it's used:** RAG training runs on every server startup. Without deduplication, the vector store would accumulate duplicate embeddings.

**Why it's good:** Idempotent writes — restarting the server 100 times produces the same vector store state. Content changes get new IDs automatically. No stale embeddings from previous content versions.

---

### 8.2 Multi-Collection Separation

**Files:** `backend/src/insightxpert/rag/store.py:43-59`

**Pattern:** Four ChromaDB collections: `qa_pairs` (few-shot examples), `ddl` (schema), `docs` (business context), `findings` (reserved).

**Why it's used:** Different types of context need independent retrieval — a schema question shouldn't surface business documentation.

**Why it's good:** Semantic search isolation. Each collection can have different embedding strategies or retrieval counts. Collections can be rebuilt independently.

---

### 8.3 Bootstrap Trainer with Fallback

**Files:** `backend/src/insightxpert/training/trainer.py`

**Pattern:** `Trainer.train_insightxpert()` tries DB-based training first (from `DatasetService`), then falls back to hardcoded Python files (`training/schema.py`, `training/documentation.py`, `training/queries.py`).

**Why it's used:** The app needs RAG context even if the datasets DB table is empty (first run, fresh deployment).

**Why it's good:** Always works — DB-driven when datasets exist, hardcoded when they don't. Hardcoded files are version-controlled, so the baseline training data is always available.

---

## 9. Conversation Management

### 9.1 Dual-Store Pattern (In-Memory + Persistent)

**Files:**
- In-memory: `backend/src/insightxpert/memory/conversation_store.py`
- Persistent: `backend/src/insightxpert/auth/conversation_store.py`

**Pattern:** Two conversation stores:
- **In-memory:** `OrderedDict` with LRU eviction and TTL expiry. Sub-millisecond lookups. Used for LLM context window.
- **Persistent (SQLite):** Durable, searchable, survives restarts. Used for history and audit.

**Why it's used:** LLM context retrieval must be fast (every message). But conversations must also survive server restarts.

**Why it's good:** Best of both worlds — memory-speed for the hot path, durability for the cold path. Hydration logic in `_prepare_chat()` loads from persistent store if in-memory is empty (e.g., after a restart).

---

### 9.2 LRU + TTL Cache

**Files:** `backend/src/insightxpert/memory/conversation_store.py:24-91`

**Pattern:** `OrderedDict` for LRU ordering, `updated_at` timestamps for TTL checks, `MAX_HISTORY_TURNS = 20` limits context window.

**Why it's used:** Without bounds, the in-memory store would grow forever. Stale conversations waste memory and could pollute LLM context.

**Why it's good:** O(1) lookups and insertions. Automatic cleanup of stale conversations (no manual expiry logic needed). The 20-turn limit prevents context window overflow.

---

### 9.3 IST Timezone Conversion

**Files:** `backend/src/insightxpert/auth/conversation_store.py:26-34`

**Pattern:** `_to_ist()` converts all timestamps to Asia/Kolkata timezone before returning to the frontend.

**Why it's used:** Built for the Techfest IIT Bombay challenge — all users are in India.

**Why it's good:** Consistent timezone display without client-side conversion logic. Simple and explicit.

---

## 10. Automations

### 10.1 Cron-Based Job Scheduler

**Files:** `backend/src/insightxpert/automations/scheduler.py:15-51`

**Pattern:** `AutomationScheduler` wraps APScheduler's `AsyncIOScheduler`. Each automation is a cron-triggered job with 5-minute misfire grace time.

**Why it's used:** Users can schedule recurring SQL queries (e.g., "check for fraud patterns every hour").

**Why it's good:** APScheduler handles cron parsing, job persistence, and misfire recovery. The 5-minute grace time means jobs run even if the scheduler was briefly down.

---

### 10.2 Multi-Query Chain Execution

**Files:** `backend/src/insightxpert/automations/scheduler.py:82-99`

**Pattern:** `_execute_automation()` runs SQL queries in sequence (topologically sorted by DAG), collects results, then evaluates triggers against the final result.

**Why it's used:** Complex automations may need multiple queries (e.g., compute aggregates, then check thresholds).

**Why it's good:** Composable — each SQL block is independent but ordered by dependencies. Trigger evaluation happens only on the final result, not intermediate steps.

---

### 10.3 Denormalized + Normalized Trigger Storage

**Files:** `backend/src/insightxpert/automations/service.py:33-93`

**Pattern:** Trigger conditions stored both as a JSON blob on the automation (flexible) and as normalized `AutomationTrigger` rows (queryable).

**Why it's used:** The JSON blob is easy to edit and display. The normalized rows enable efficient database queries (e.g., "find all automations with threshold triggers").

**Why it's good:** Both representations are always in sync (written atomically). Each serves its purpose — blob for flexibility, rows for queryability.

---

## 11. Frontend State Management

### 11.1 Zustand with Persist Middleware

**Files:** `frontend/src/stores/chat-store.ts`

**Pattern:** Zustand store with `persist` middleware to sessionStorage. Conversations stored without messages (messages lazy-loaded per conversation).

**Why it's used:** The app needs persistent state (conversation list, sidebar state) across page reloads, but full message history is too large for sessionStorage.

**Why it's good:**
- **Minimal footprint:** Only conversation metadata persists; messages load on-demand
- **Fast hydration:** sessionStorage is synchronous — no loading spinner for the conversation list
- **No boilerplate:** Zustand's API is ~10x less code than Redux

---

### 11.2 Optimistic Updates with Rollback

**Files:** `frontend/src/stores/notification-store.ts`, `stores/settings-store.ts`

**Pattern:** Save previous state, apply update immediately, revert on API failure:
```typescript
const prev = get();
set({ /* optimistic */ });
apiCall().catch(() => set(prev));
```

**Why it's used:** Marking notifications as read and switching models should feel instant.

**Why it's good:** Zero perceived latency for the user. If the API fails, the UI reverts seamlessly. No loading spinners for low-risk operations.

---

### 11.3 Fire-and-Forget API Calls

**Files:** `frontend/src/stores/chat-store.ts` (delete, rename), `components/chat/message-list.tsx` (feedback)

**Pattern:** `apiFetch(url, options).catch(() => {})` — no await, no loading state.

**Why it's used:** Operations like deleting a conversation or submitting feedback don't need to block the UI.

**Why it's good:** The UI remains responsive even if the API is slow or offline. Acceptable for operations where eventual consistency is fine.

---

### 11.4 Derived Selectors

**Files:** `frontend/src/stores/chat-store.ts` (activeConversation), `components/chat/message-bubble.tsx` (selectIsActiveStreaming)

**Pattern:** Computed values derived on-demand from store state:
```typescript
activeConversation: () => {
  const { conversations, activeConversationId } = get();
  return conversations.find(c => c.id === activeConversationId) || null;
}
```

**Why it's used:** Avoids storing derived state that can become stale.

**Why it's good:** Always consistent with source state. No synchronization bugs. Zustand's fine-grained subscriptions ensure components only re-render when the derived value actually changes.

---

### 11.5 Topological Sort for Workflow DAG

**Files:** `frontend/src/stores/automation-store.ts:30-72`

**Pattern:** Kahn's algorithm sorts workflow SQL blocks by dependency edges. Disconnected blocks fall back to Y-position order.

**Why it's used:** Automation workflows are visual DAGs (directed acyclic graphs). SQL queries must execute in dependency order.

**Why it's good:** Handles complex multi-block workflows correctly. The Y-position fallback means even unconnected blocks have a predictable order (top-to-bottom visual layout).

---

## 12. Frontend Component Patterns

### 12.1 Chunk Type Dispatch

**Files:** `frontend/src/components/chunks/chunk-renderer.tsx:76-159`

**Pattern:** Switch on `chunk.type` to render type-specific components:
- `status` → progress indicator
- `sql` → code block
- `tool_result` → data table + chart
- `answer` → markdown renderer
- `clarification` → interactive buttons
- `error` → error message

**Why it's used:** The SSE stream produces heterogeneous chunks. Each type needs different rendering.

**Why it's good:** Clean separation — each chunk type has its own component. Adding a new chunk type is a new case in the switch + a new component file.

---

### 12.2 Responsive Layout with Framer Motion

**Files:** `frontend/src/components/layout/app-shell.tsx`

**Pattern:** Desktop: `AnimatePresence` + `motion.aside` for sidebars. Mobile: Radix `Sheet` (slide-in panels).

**Why it's used:** Desktop users expect persistent sidebars. Mobile users need full-screen content with slide-in panels.

**Why it's good:** `useIsMobile()` hook switches between layouts at the component level, not with CSS media queries. Framer Motion provides smooth width animations (308px → 0) that CSS `display: none` can't match.

---

### 12.3 Stable Callback Wrappers

**Files:** `frontend/src/components/chat/message-bubble.tsx:93-98`, `message-list.tsx:37-49`

**Pattern:** Parent provides a stable `onFeedback(messageId, type, comment)` callback. Each `MessageBubble` wraps it with `useCallback` to bind its specific `message.id`:
```typescript
const handleFeedbackForMsg = useCallback(
  (type, comment) => onFeedback?.(message.id, type, comment),
  [message.id, onFeedback],
);
```

**Why it's used:** Without stable callbacks, every parent re-render creates new function references, breaking `React.memo` on child components.

**Why it's good:** Enables effective memoization. The parent's callback is stable (defined once with `useCallback([], [])`). Each child's wrapper is stable per message ID. Together, they prevent cascade re-renders when sibling messages update.

---

### 12.4 Zustand Subscription in useEffect

**Files:** `frontend/src/components/chat/message-input.tsx`

**Pattern:** Direct Zustand subscription to watch for `pendingInput`:
```typescript
useEffect(() => {
  return useChatStore.subscribe((state) => {
    if (state.pendingInput) {
      state.setPendingInput(null);
      // auto-fill and optionally auto-send
    }
  });
}, [onSend]);
```

**Why it's used:** The clarification "Just answer" button sets `pendingInput` in the store. The input component needs to react to this without causing a render loop.

**Why it's good:** Direct subscription avoids the selector → re-render → effect cycle. The component only processes the event once, then clears `pendingInput`. Clean unsubscribe on unmount.

---

## 13. Frontend Performance

### 13.1 React.memo with Custom Comparators

**Files:** `message-bubble.tsx:194-202`, `answer-chunk.tsx:114`, `chart-block.tsx:260`

**Pattern:** Expensive components wrapped with `React.memo` and custom equality functions that compare only the props that matter.

**Why it's used:** A chat with 50 messages re-renders the entire list when any message updates. Without memo, markdown parsing, chart rendering, and DOM diffing run for all 50 messages.

**Why it's good:** Only the changed message re-renders. Custom comparators ensure memo doesn't break on reference-unequal-but-value-equal props.

---

### 13.2 Lazy Chart Loading with IntersectionObserver

**Files:** `frontend/src/components/chunks/chart-block.tsx:266-295`

**Pattern:** Charts render only when near the viewport (200px margin). Streaming charts skip the observer (`eager={true}`).

**Why it's used:** Recharts rendering is expensive. A conversation with 20 charts would cause significant jank on load.

**Why it's good:** Off-screen charts pay zero cost. The 200px margin pre-loads just before the user scrolls to them, so there's no visible delay. Streaming charts render immediately (the user is watching them).

---

### 13.3 Microtask Batching in SSE Client

**Files:** `frontend/src/lib/sse-client.ts:25-37`

**Pattern:** SSE chunks are queued and drained via `queueMicrotask()`:
```typescript
function enqueue(data) {
  chunkQueue.push(data);
  if (!draining) {
    draining = true;
    queueMicrotask(drainQueue);
  }
}
```

**Why it's used:** A single `reader.read()` call may contain multiple SSE events. Processing each one individually causes multiple React state updates.

**Why it's good:** All chunks from the same read are processed in one microtask. React 18's automatic batching then combines all state updates into a single render. This eliminated the 16ms stagger between chunks that was causing visible jitter.

---

### 13.4 Smart Auto-Scroll Dependencies

**Files:** `frontend/src/components/chat/message-list.tsx:20`, `hooks/use-auto-scroll.ts`

**Pattern:** Auto-scroll triggers on `[messages.length, lastMsgChunkCount]` — NOT on feedback, tokens, wallTimeMs, or other metadata changes.

**Why it's used:** Early versions auto-scrolled on every state change, causing DOM reflow when the user was reading earlier messages.

**Why it's good:** Only scrolls when new messages arrive or the current message grows (streaming). Metadata updates (like feedback submission or token counts) don't cause unwanted scrolling.

---

### 13.5 SessionStorage Persistence without Messages

**Files:** `frontend/src/stores/chat-store.ts`

**Pattern:** Zustand's `persist` middleware saves conversation metadata to sessionStorage, but messages are excluded. Messages lazy-load from the API when a conversation is activated.

**Why it's used:** A conversation with 100 messages and large tool results could be megabytes. SessionStorage has a ~5MB limit.

**Why it's good:** Fast page loads (only metadata to parse). Messages load on-demand with minimal latency. No risk of hitting storage limits.

---

## 14. Infrastructure & Deployment

### 14.1 Monorepo with Independent Stacks

**Structure:**
```
/backend/   — Python (FastAPI, uv)
/frontend/  — TypeScript (Next.js, npm)
/.github/   — CI/CD (GitHub Actions)
```

**Why it's used:** Backend and frontend have different languages, package managers, and deployment targets.

**Why it's good:** Single repo for atomic commits across the stack. Independent dependency management (uv vs npm). CI/CD can test and deploy each independently.

---

### 14.2 Docker Layer Caching

**Files:** `backend/Dockerfile`

**Pattern:** Dependencies copied and installed before source code:
```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/ src/
```

**Why it's used:** Source code changes more frequently than dependencies.

**Why it's good:** Dependency installation is cached unless `pyproject.toml` or `uv.lock` changes. A typical code change rebuilds only the final `COPY` layer — seconds instead of minutes.

---

### 14.3 ONNX Model Warmup at Build Time

**Files:** `backend/Dockerfile`

**Pattern:** Pre-downloads ChromaDB's ONNX embedding model during Docker build:
```dockerfile
RUN uv run python -c "from chromadb.utils...; ef(['warmup'])"
```

**Why it's used:** ChromaDB downloads the embedding model on first use. In Cloud Run, cold starts have tight timeouts.

**Why it's good:** The embedding model is baked into the Docker image. Cold starts don't need network access for model downloads.

---

### 14.4 Workload Identity Federation (Keyless GCP Auth)

**Files:** `.github/workflows/deploy.yml`

**Pattern:** GitHub Actions authenticates to GCP using Workload Identity Federation — no service account JSON keys in secrets.

**Why it's used:** JSON key files are long-lived secrets that can be leaked. WIF uses short-lived OIDC tokens.

**Why it's good:** No secrets to rotate. Token lifetime is minutes, not years. GitHub's OIDC provider is trusted by GCP directly.

---

### 14.5 Firebase Hosting with Cloud Run Backend

**Files:** `firebase.json`

**Pattern:**
- Static frontend served from Firebase CDN
- API requests rewritten to Cloud Run backend
- SPA fallback: `**` → `/index.html`
- Immutable cache headers for static assets (1 year)

**Why it's used:** Firebase CDN provides global edge caching for the frontend. Cloud Run provides auto-scaling for the backend.

**Why it's good:** Frontend loads from the nearest CDN edge (sub-100ms). API requests route directly to Cloud Run (no double-hop). Static assets are aggressively cached — only the HTML needs to be fresh.

---

### 14.6 Conditional Static Export

**Files:** `frontend/next.config.ts`

**Pattern:** `NEXT_OUTPUT=export` triggers Next.js static HTML generation. Without it, Next.js runs in dev mode with API rewrites.

**Why it's used:** Production deploys to Firebase Hosting (static files only). Development needs a proxy to the local backend.

**Why it's good:** Same codebase, same build command, different output. No separate "static" and "dynamic" frontends to maintain.

---

## 15. Error Handling

### 15.1 Custom Exception Hierarchy

**Files:** `backend/src/insightxpert/exceptions.py`

**Pattern:** Base `InsightXpertError` with subclasses: `DatabaseConnectionError`, `QuerySyntaxError`, `QueryTimeoutError`, `LLMError`. Each has pre-set HTTP status codes and error codes.

**Why it's used:** Different error types need different HTTP responses (400 vs 503 vs 500) and different client-side handling.

**Why it's good:** Structured, type-safe error handling. Global exception handlers in `main.py` map each exception class to the correct HTTP response. Adding a new error type is a new subclass — the handler is already generic.

---

### 15.2 Global Exception Handlers with CORS Awareness

**Files:** `backend/src/insightxpert/main.py:533-603`

**Pattern:** Four exception handlers:
1. `InsightXpertError` → JSON with error code
2. `RequestValidationError` → field-level errors flattened to string
3. `HTTPException` → CORS-aware response
4. Generic `Exception` → 500 with CORS headers manually added

**Why it's used:** Starlette's `ServerErrorMiddleware` (outermost) intercepts generic exceptions BEFORE `CORSMiddleware` adds headers. Without manual CORS headers, 500 errors are invisible to the browser (blocked by CORS).

**Why it's good:** Every error response is browser-readable, even 500s. No silent CORS failures. Full tracebacks logged server-side, sanitized messages sent to client.

---

## 16. Observability

### 16.1 Structured Logging with Module Names

**Files:** Throughout the backend

**Pattern:** `logging.getLogger(__name__)` per module. Formatted with ANSI colors, timestamps, and module paths. Noisy libraries (chromadb, httpcore, httpx) quieted to WARNING.

**Why it's used:** A multi-module async application needs clear log attribution.

**Why it's good:** Every log line identifies its source module. Color coding makes manual log reading fast. Quieting noisy libraries keeps the signal-to-noise ratio high.

---

### 16.2 Query Timing Instrumentation

**Files:** `backend/src/insightxpert/db/connector.py:100-115`

**Pattern:** `execute()` measures elapsed time and logs SQL, duration, and row count.

**Why it's used:** Slow queries are the #1 performance issue in data analytics apps.

**Why it's good:** Every query is timed automatically — no per-query instrumentation needed. Slow queries stand out in logs immediately. Combined with the token counting wrapper, you get full end-to-end visibility: LLM time + DB time + network time.

---

### 16.3 Client-Side Wall Clock Timing

**Files:** `frontend/src/hooks/use-sse-chat.ts:46,211`

**Pattern:** Records `Date.now()` before sending, calculates `wallTimeMs = Date.now() - sendTime` after stream completes.

**Why it's used:** Server-side `generation_time_ms` excludes network latency and persistence time. The client's wall clock is the true user-perceived latency.

**Why it's good:** Comparing `wallTimeMs` vs `generation_time_ms` instantly reveals if latency is in the server, the network, or persistence. This is how the 37s vs 17s latency gap was diagnosed and fixed.

---

## Summary: Pattern Categories

| Category | Count | Key Patterns |
|----------|-------|--------------|
| **Async Architecture** | 4 | Lifespan context manager, `asyncio.to_thread`, fire-and-forget, lazy init |
| **Database** | 7 | Adapter wrapper, dialect pooling, WAL pragmas, bidirectional sync, idempotent migrations, delete tracking, read-only mode |
| **Auth & Security** | 5 | JWT cookies, bcrypt, DI auth, domain admin detection, scope-based access |
| **LLM Integration** | 4 | Protocol abstraction, factory with lazy imports, format translation, token counting wrapper |
| **Agent System** | 5 | Tool registry, tool context, shared loop, multi-phase orchestrator, chunk interception |
| **API & Streaming** | 5 | SSE, fire-and-forget persist, feature layering, SQL validation, payload truncation |
| **RAG** | 3 | Content-addressable dedup, multi-collection, fallback training |
| **Conversations** | 3 | Dual-store, LRU+TTL cache, IST conversion |
| **Automations** | 3 | Cron scheduler, chain execution, dual storage |
| **Frontend State** | 5 | Zustand persist, optimistic updates, fire-and-forget, derived selectors, topological sort |
| **Frontend Components** | 4 | Chunk dispatch, responsive layout, stable callbacks, store subscriptions |
| **Frontend Performance** | 5 | React.memo, lazy charts, microtask batching, smart scroll deps, storage without messages |
| **Infrastructure** | 6 | Monorepo, Docker caching, ONNX warmup, WIF auth, Firebase+Cloud Run, conditional export |
| **Error Handling** | 2 | Exception hierarchy, CORS-aware global handlers |
| **Observability** | 3 | Structured logging, query timing, client wall clock |
| **Total** | **64** | |
