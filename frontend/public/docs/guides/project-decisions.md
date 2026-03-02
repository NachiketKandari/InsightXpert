# InsightXpert: Project Decision History

> **Note:** This document is gitignored. It chronicles every architectural, engineering, and product decision made during the development of InsightXpert from inception to its final state, along with the probable reasoning behind each choice. Written for future developers (or the same developer six months later) who need to understand not just *what* was built but *why*.

---

## Project Context

InsightXpert is an AI data analyst for the Techfest IIT Bombay Leadership Analytics Challenge. It queries 250K Indian digital payment (UPI) transactions via natural language using a custom multi-agent pipeline (FastAPI + Gemini/Ollama + ChromaDB + Turso/libSQL), deployed on Firebase Hosting + Cloud Run.

Development ran from **Feb 14 to Feb 26, 2026** — 12 days, ~100 commits across 6 phases.

---

## Table of Contents

1. [Phase 1: Project Inception & Core Architecture](#phase-1-project-inception--core-architecture-feb-14-early)
2. [Phase 2: Design Patterns, Charting & Conversation Search](#phase-2-design-patterns-charting--conversation-search-feb-14-mid)
3. [Phase 3: CI/CD, Firebase Deployment & Auth Hardening](#phase-3-cicd-firebase-deployment--auth-hardening-feb-14-late)
4. [Phase 4: Database Migration (SQLite → Turso) & Mobile UI](#phase-4-database-migration-sqlite--turso--mobile-ui-feb-14-15)
5. [Phase 5: UI Polish, Admin Panel & Real Data](#phase-5-ui-polish-admin-panel--real-data-feb-14-18)
6. [Phase 6: Streaming Hardening, Benchmarks, Security & Phase 0 Cleanup](#phase-6-streaming-hardening-benchmarks-security--phase-0-cleanup-feb-17-26)

---

# Phase 1: Project Inception & Core Architecture (Feb 14, Early)

## Overview

Phase 1 established the complete full-stack skeleton of InsightXpert in a single day (Feb 14, 2026), building a from-scratch SQL agent engine to replace an earlier Vanna prototype. The initial commit delivered 129 files — a working FastAPI backend with a tool-calling LLM agent, ChromaDB RAG, JWT auth, persistent conversations, and a Next.js chat frontend with SSE streaming. Three follow-up commits the same day formalized the extension-point design patterns (LLM Factory, Tool Registry, VectorStore Protocol), hardened error handling, and added message action buttons and feedback collection.

---

## Decisions Made

### Build a From-Scratch SQL Agent Instead of Using Vanna

**What:** The project explicitly abandoned Vanna (a third-party text-to-SQL library) and replaced it with a custom agent loop in `agents/analyst.py` (~273 lines at initial commit). ARCHITECTURE.md documents this directly: "Vanna was replaced with a from-scratch engine (~600 lines across analyst, tools, LLM providers, RAG store)."

**Why (probable):** Vanna's single-shot SQL generation model did not fit the multi-step reasoning the project required. The evaluation rubric weighted Insight Accuracy (30%), Explainability (20%), and Conversational Quality (15%) — all of which demand more than one-shot SQL generation. A custom loop gives full control over: (1) multi-turn tool-calling where the LLM can inspect schema, run intermediate SQL, and self-correct; (2) the exact format of the streamed response (5-layer structure: direct answer, evidence, provenance, caveats, follow-ups); (3) injection of RAG context into each iteration; and (4) auto-saving learned Q→SQL pairs back into ChromaDB. The comment in ARCHITECTURE.md lists five explicit rationale points: custom agent loop, multi-agent orchestration path, full explainability control, custom SSE streaming, and observability hooks.

**Commits:** `8742a10`

---

### Technology Stack — FastAPI + Next.js + SQLite

**What:** Backend is FastAPI (Python 3.11+) with SQLAlchemy, served via uvicorn. Frontend is Next.js 16 with React 19. The analytics database is SQLite. The auth/conversation database is a separate SQLite file (`insightxpert_auth.db`).

**Why (probable):** FastAPI was the natural choice for a Python-native LLM backend: async-first (necessary for SSE streaming and concurrent LLM calls), automatic OpenAPI docs (useful for the Postman collection included in the initial commit), and Pydantic for request/response validation. SQLite was the right fit given the problem constraints: a fixed, read-only 250K-row dataset that fits comfortably in a single file (~80MB). There is no write workload on the analytics side, which eliminates all operational concerns about concurrent writes. Next.js 16/React 19 gives the newest stable Next.js with React Server Components support and the App Router, which simplifies route-based auth guards.

**Commits:** `8742a10`

---

### Synthetic Data Generation (250K Transactions, Indian Digital Payments)

**What:** `backend/generate_data.py` generates 250,000 synthetic Indian digital payment transactions into SQLite with 17 columns. Key design choices: transaction types (P2P, P2M, Bill Payment, Recharge) with realistic NULL semantics (merchant_category is NULL for P2P; receiver_age_group is NULL for non-P2P); log-normal amount distributions per transaction type; fraud_flag with a layered probability model (3% base + 5% for large amounts + 2% for late-night hours); age and device type weighted distributions (Android 60%, iOS 25%); 9 composite indices on high-cardinality filter columns; reproducible via `random.seed(42)`.

**Why (probable):** The Techfest PRD specifies a synthetic Indian digital payment dataset. Synthetic data serves several purposes simultaneously: it avoids any real PII or regulatory data concerns; it can be engineered to contain interesting patterns (the biased fraud probability, the NULL semantics for P2P vs. merchant transactions) that make the analyst's answers more interesting to evaluate; and the 17-column schema with domain-specific vocabulary (UPI-era banks: SBI, HDFC, ICICI; Indian states; INR amounts) grounds the natural language queries in a realistic business context. The `random.seed(42)` ensures every developer and evaluator gets identical data. The composite indices on transaction_type, status, merchant_category, fraud_flag, hour_of_day, and weekend flag anticipate the exact filter patterns the evaluation questions probe.

**Commits:** `8742a10`

---

### Gemini as Primary LLM, Ollama as Local Fallback

**What:** `config.py` defines a `LLMProvider` enum with `GEMINI` (default) and `OLLAMA`. The frontend ships with a runtime model switcher in the header. The backend exposes `POST /api/config/switch` to hot-swap the provider without a restart. Initial Gemini model default is `gemini-2.5-flash`.

**Why (probable):** Gemini 2.5 Flash is a high-capability model with generous free-tier access, making it suitable for a hackathon submission where budget is unconstrained but the API key needs to be shareable. Ollama provides a local offline fallback critical for development without internet or for demo environments where a live API key cannot be guaranteed. The runtime switching exists because the demo scenario (a live presentation at IIT Bombay) may require switching between a fast cloud model and a local model mid-demo. Gemini 2.5 Flash — rather than 2.5 Pro — was chosen as the default, probably to manage latency and cost during iterative testing while keeping Pro available for accuracy-critical runs.

**Commits:** `8742a10`

---

### ChromaDB for RAG Vector Store (Four Separate Collections)

**What:** `rag/store.py` wraps ChromaDB's `PersistentClient` and creates four separate named collections: `qa_pairs` (example question→SQL pairs), `ddl` (schema DDL strings), `docs` (business documentation), `findings` (anomaly/analysis findings). SHA256-derived IDs enable automatic deduplication via `upsert`. The RAG store is bootstrapped on every startup via `Trainer.train_insightxpert()`, which loads the static DDL, documentation, and ~12 example queries.

**Why (probable):** Four separate collections rather than one unified collection gives semantic search scope control. When the analyst is forming a SQL query, it queries qa_pairs (for similar past questions) and ddl (for schema hints) separately, each with different `n` values. Mixing them into one collection would require metadata filters and would dilute the embedding space. ChromaDB was chosen over alternatives (FAISS, Milvus, Pinecone) because it runs embedded in-process with no external service, stores persistently to disk, and requires zero configuration — all appropriate for a hackathon project. The findings collection is pre-registered (but initially empty) because the ARCHITECTURE.md plans an Anomaly Detector agent that would populate it.

**Commits:** `8742a10`

---

### Dual Conversation Store (In-Memory LRU + SQLite-Persistent)

**What:** Two parallel conversation stores exist from day one. An in-memory `OrderedDict` with LRU eviction (max 500 conversations) and TTL expiry (2 hours) — stores only user messages and final assistant answers (not intermediate tool call/result pairs). A SQLAlchemy-backed `PersistentConversationStore` that writes to `insightxpert_auth.db` and stores the full `chunks_json` blob alongside each message.

**Why (probable):** The two stores serve different purposes and operate at different latencies. The in-memory store is the LLM context source: it is read on every chat request to build the multi-turn conversation history injected into the system prompt, so it must be fast and must exclude noisy tool intermediaries (which would consume context tokens without providing conversational value). The persistent store is the history replay source: it is written after each exchange and read only when a user loads an old conversation or the sidebar is populated. Separating them avoids the cost of deserializing full chunk blobs on every LLM call. The TTL/LRU eviction on the in-memory store prevents unbounded growth on a long-running server.

**Commits:** `8742a10`

---

### JWT Authentication with httpOnly Cookies (Separate Auth SQLite)

**What:** `auth/security.py` implements HS256 JWT tokens with bcrypt password hashing. `auth/dependencies.py` reads the token from `request.cookies.get("access_token")` — an httpOnly cookie, not a Bearer header. The auth schema (users, conversations, messages) lives in a separate `insightxpert_auth.db` SQLAlchemy engine from the analytics `insightxpert.db`. A seed admin user is created on startup via `auth/seed.py`.

**Why (probable):** httpOnly cookies prevent XSS-based token theft: a malicious script injected into the page cannot read `document.cookie` for httpOnly cookies. This is superior to localStorage-based token storage for a production-demo app where the auth model needs to appear robust to evaluators. The choice of a separate SQLite file for auth and analytics is defensive: the analytics database is a generated read-only dataset that can be wiped and regenerated at any time without affecting user sessions or conversation history. The seeded admin user eliminates signup friction during demos. The `access_token_expire_minutes: int = 1440` default (24 hours) is deliberately long for demo use.

**Commits:** `8742a10`

---

### Pydantic Settings for Configuration

**What:** `config.py` uses `pydantic_settings.BaseSettings` with `env_file=".env.local"`. All tuneable parameters (LLM provider, API keys, database URLs, agent iteration limits, SQL row limit, auth secret key, log level) are declared as typed fields with defaults.

**Why (probable):** `pydantic-settings` provides the exact configuration pattern needed for a project that must run in three environments: local development (`.env.local` file), CI (environment variables), and Cloud Run deployment (environment variables injected at runtime). Typed fields with defaults mean the app starts with sane behavior even with a minimal `.env.local`. The `db_type` property shows forward-thinking: though SQLite is the initial database, the settings model already parses PostgreSQL and MySQL URLs, accommodating the Cloud Run deployment that later would require Turso (libSQL/SQLite-compatible over HTTP).

**Commits:** `8742a10`

---

### SSE Streaming for Chat Responses

**What:** The primary chat endpoint is `POST /api/chat` which returns an `EventSourceResponse` (from `sse-starlette`). Each agent step yields a typed `ChatChunk` Pydantic model serialized as JSON SSE data. A polling fallback `POST /api/chat/poll` accumulates all chunks and returns them as a JSON array. The frontend implements a custom `createSSEStream()` function in `lib/sse-client.ts` rather than using the browser's `EventSource` API.

**Why (probable):** SSE is the correct protocol for this use case: unidirectional server-to-client streaming over HTTP/1.1, no WebSocket handshake overhead, automatic reconnect semantics, and proxy-friendly. The agent loop can take 5–30 seconds (multiple LLM calls + SQL execution), and streaming each step (status, sql, tool_call, tool_result, answer) gives the user live feedback rather than a blank screen. The custom `fetch`-based SSE client (rather than `EventSource`) was necessary because `EventSource` does not support POST requests or custom headers — the chat endpoint is a POST with a JSON body and needs to send the `credentials: "include"` header for cookie auth. The polling endpoint exists as a fallback for environments where SSE is unreliable (some corporate proxies strip chunked responses).

**Commits:** `8742a10`

---

### Zustand for Frontend State Management

**What:** The frontend uses three Zustand stores: `chat-store.ts` (conversation list, active conversation, streaming state, agent steps, sidebar toggles), `auth-store.ts` (user identity, login/logout/checkAuth), and `settings-store.ts`. The chat store uses a flat action model where `appendChunk` mutates the last assistant message in place.

**Why (probable):** Zustand is the minimal-footprint alternative to Redux for a project that does not need the full Redux DevTools/middleware ecosystem. The separation into three stores reflects the separation of concerns: auth state rarely changes and is read by many components; settings state is mostly read by the model selector; chat state mutates constantly during streaming and is consumed by the chat panel. Using `create` without a persistence middleware is intentional: conversation history is fetched from the backend on `initFromStorage()`, not stored in localStorage, keeping the client thin.

**Commits:** `8742a10`

---

### Shadcn UI Component Library

**What:** `frontend/components.json` configures shadcn. The initial commit contains 15+ Shadcn-derived components: button, card, badge, input, textarea, scroll-area, separator, sheet, skeleton, tooltip, dropdown-menu, collapsible, avatar, and a full chart component wrapping recharts.

**Why (probable):** Shadcn generates owned, editable components rather than importing from a black-box npm package — each component is a file in `src/components/ui/` that can be modified freely. For a demo project with a two-week deadline, this means the team can accept the defaults for standard UI elements while having full control over domain-specific components (the chunk renderers, the agent step timeline) without fighting an opinionated component library. The Tailwind CSS 4 integration is tight and the dark mode theming is handled by CSS variables.

**Commits:** `8742a10`

---

### LLM Factory Pattern (Registry-Based Provider Creation)

**What:** `llm/factory.py` (introduced in `892b998`) defines a module-level `_REGISTRY` dict mapping provider name strings to factory functions. `create_llm(provider, settings)` looks up the registry and calls the appropriate factory. The initial `main.py` had an if/else block for Gemini vs Ollama; `api/routes.py` had a second if/else block in the `switch_model` endpoint. Both were replaced with `create_llm()` calls.

**Why (probable):** The duplication between `main.py` and `api/routes.py` was the immediate trigger: two if/else blocks for the same LLM instantiation logic meant adding a third provider would require editing two files. The registry pattern centralizes provider registration and makes the dispatch table explicit. Lazy imports inside each factory function avoid importing both the `google-genai` and `ollama` packages at startup when only one provider is active.

**Commits:** `892b998`

---

### Tool ABC + ToolRegistry Pattern

**What:** `agents/tool_base.py` (introduced in `892b998`) defines an abstract `Tool` base class with `name`, `description`, `get_args_schema()`, and `async execute(context, args)` abstract methods. `ToolRegistry` is a plain dict-backed class with `register()`, `get_schemas()`, and `async execute()` methods. The original `tools.py` had a flat `execute_tool()` function with an if/elif chain dispatching by tool name.

**Why (probable):** The if/elif chain is the classic pre-refactoring code smell for this kind of dispatch. Each new tool requires modifying the chain in two places: the JSON schema list and the elif branch. The ABC + registry pattern makes each tool a self-contained unit with its own schema and execution logic. The `ToolContext` dataclass bundles the dependencies (DatabaseConnector, VectorStore, row_limit) that all tools need, avoiding threading individual parameters through every call. `ToolRegistry.execute()` wraps all tool calls in try/except with traceback logging, centralizing error handling that was previously duplicated.

**Commits:** `892b998`

---

### VectorStoreBackend Protocol

**What:** `rag/base.py` (introduced in `892b998`) defines a `@runtime_checkable` `VectorStoreBackend` Protocol declaring eight methods: `add_qa_pair`, `add_ddl`, `add_documentation`, `add_finding`, `search_qa`, `search_ddl`, `search_docs`, `search_findings`. A companion `rag/memory.py` provides an `InMemoryVectorStore` implementing the same protocol using plain Python dicts for testing.

**Why (probable):** The Protocol approach decouples all consumers from ChromaDB without requiring them to inherit from an abstract base class — Python's structural subtyping means `VectorStore` implements the protocol implicitly. The `runtime_checkable` decorator enables `isinstance(rag, VectorStoreBackend)` assertions in tests. The `InMemoryVectorStore` was the concrete motivation: tests that instantiate a full ChromaDB client are slow and require disk I/O. The in-memory implementation satisfies the protocol and makes unit tests fast and hermetic.

**Commits:** `892b998`

---

### Error Handling Philosophy — Surface Errors as Chat Messages, Not Crashes

**What:** Commit `263d8c1` wraps the LLM `chat()` call in `analyst.py` in a try/except that yields a `ChatChunk(type="error", content=f"LLM request failed: {exc}")` and returns from the generator rather than propagating the exception. The Ollama provider received a 120-second timeout, and the `switch_model` endpoint validates that the requested Ollama model exists before accepting the switch (returning 503 if not).

**Why (probable):** An SSE generator that raises an uncaught exception produces a half-terminated stream: the frontend receives some chunks, then the connection closes with no `[DONE]` sentinel and no error chunk. The user sees a frozen loading state with no indication of what went wrong. By catching exceptions inside the generator and yielding an error chunk, the stream terminates cleanly, the frontend renders the error inline in the chat, and the `[DONE]` sentinel still arrives. The Ollama model validation at switch time prevents a subtler failure mode: the user switches to a model that isn't pulled, subsequent chat requests fail with a cryptic 404 from Ollama — validating early gives a clearer 503 error at the point of configuration.

**Commits:** `263d8c1`

---

### get_or_create_conversation for Frontend-Generated IDs

**What:** The frontend generates conversation IDs client-side via `Math.random().toString(36).slice(2, 10)` in `newConversation()`. These IDs are sent to the backend in the first chat request as `conversation_id`. Commit `263d8c1` added `get_or_create_conversation(conversation_id, user_id, title)` to `PersistentConversationStore`: it attempts `session.get(ConversationRecord, conversation_id)` first and creates a new record with the provided ID if none exists.

**Why (probable):** The initial implementation had a bug: if the frontend sent a `conversation_id` that didn't exist in the backend database, the backend would try to save the message with a foreign key to a non-existent conversation and fail silently. The fix uses the frontend-provided ID as the actual primary key (rather than generating a new UUID server-side) so that the frontend's local state and the backend's persisted state share the same ID without a round-trip. This is the "optimistic creation" pattern common in offline-first applications. The ownership check prevents one user from hijacking another user's conversation by guessing their ID.

**Commits:** `263d8c1`

---

### Message Action Buttons and Feedback Endpoint (Added Day One)

**What:** Commit `263d8c1` added a `MessageActions` component with copy (clipboard), thumbs up, thumbs down (with optional comment input), and retry (last assistant message only) buttons as a hover toolbar on each message bubble. The backend received `POST /api/feedback` backed by a new `FeedbackRecord` SQLAlchemy model.

**Why (probable):** The evaluation rubric includes Conversational Quality (15%) and Innovation (10%). Thumbs feedback infrastructure signals that the product is instrumented to learn and improve — this is table stakes for any production AI assistant. Adding it on day one rather than as a polish item ensures the feedback loop is real (data is written to the database and could feed future RAG improvements) rather than cosmetic. The retry button specifically addresses a common demo scenario: the LLM occasionally produces a wrong or incomplete answer, and the ability to retry without retyping the question reduces friction.

**Commits:** `263d8c1`

---

### Orchestrator as a Stub with Planned Multi-Agent Pipeline

**What:** `agents/orchestrator.py` in the initial commit is 6 lines: a module docstring describing the planned analyst → statistician → narrator pipeline and a note that `analyst_loop` is called directly from routes for now. No Statistician, Creative Narrator, or Anomaly Detector agents exist.

**Why (probable):** Building the orchestrator stub communicates the intended extension point without blocking the working end-to-end demo. The file exists in the repo so the directory structure reflects the planned architecture in code, not just in documentation. The decision to call `analyst_loop` directly from routes (bypassing the orchestrator) was pragmatic: the orchestrator would add latency and complexity that is not justified until the downstream agents exist.

**Commits:** `8742a10`

---

## Key Patterns Established in Phase 1

**Tool-calling agent loop as the core abstraction.** The `analyst_loop` generator function — RAG retrieval, system prompt construction, iterative LLM + tool execution, auto-save of learned Q→SQL pairs — is the central pattern that all subsequent agent work extends.

**Typed SSE chunk protocol.** The `ChatChunk` Pydantic model with a `type` discriminator field (`status`, `sql`, `tool_call`, `tool_result`, `answer`, `error`) established the frontend/backend contract for streaming. This protocol was never broken across phases.

**Dual-store conversation model.** The split between a fast in-memory LRU store (for LLM context injection) and a persistent SQLite store (for history replay) accommodates both the multi-turn conversational requirement and the UI requirement to reload past conversations.

**ABC + Registry for all extension points.** The LLM Factory, Tool Registry, and VectorStore Protocol established the pattern: concrete implementations are registered/discovered by name; consumers depend on abstract interfaces; new implementations can be added without modifying existing code.

**Error-as-data philosophy.** Rather than letting exceptions propagate through the SSE generator, all errors are caught and yielded as `ChatChunk(type="error")` objects. This means the frontend always receives a well-formed response.

---

# Phase 2: Design Patterns, Charting & Conversation Search (Feb 14, Mid)

## Overview

Phase 2 continued on the same day as Phase 1, spanning nine commits. The work falls into three thematic groups: internal code quality (Jinja2 template extraction, settings mutation fix, internals hardening), a complete chart rendering layer (pie chart, grouped bar, color palette, chart awareness in the LLM), and frontend UX depth (table/chart card separation, spinner completion states, conversation search). Two pull requests merged the work: PR #1 (`design-patterns`) and PR #2 (conversation search).

Phase 2 did not change the fundamental architecture established in Phase 1. Instead it addressed the first crop of bugs that appeared once the system was running end-to-end, and added the visualization and search features that turn the data analyst from a text-only tool into something that can genuinely aid leadership audiences.

---

## Decisions Made

### Extract Analyst System Prompt to Jinja2 Template

**What:** The `SYSTEM_PROMPT_TEMPLATE` string and `_build_system_prompt()` function were removed from `analyst.py` (85 lines deleted) and replaced with `prompts/analyst_system.j2` (70 lines) plus a reusable `prompts/__init__.py` `render()` function. Conditional assembly of RAG sections moved from Python string concatenation into `{% if %}/{% for %}` Jinja2 blocks. Call sites became `render_prompt("analyst_system.j2", ddl=DDL, documentation=DOCUMENTATION, similar_qa=..., ...)`.

**Why (probable):** Three distinct problems drove this. First, the prompt was a Python f-string, meaning sections that should only appear when RAG results exist were present as empty headers with empty content — the template's `{% if similar_qa %}` block eliminates those empty sections cleanly. Second, the `_build_system_prompt()` function was a concatenation loop that duplicated the section-ordering logic. Third, as the prompt grew (the Visualization section was added two commits later), editing a `.j2` file is safer than editing a multi-line Python string — syntax errors in `.j2` files are caught at render time with clear line numbers. The `autoescape=False` flag is correct here: these are plain-text prompts, not HTML templates, and autoescaping would corrupt SQL DDL content that contains `<`, `>`, or `&`.

**Commits:** `e6afc28`

---

### Settings Mutation Bug on LLM Switch

**What:** The original `switch_model` endpoint mutated `settings.llm_provider`, `settings.gemini_model`, and `settings.ollama_model` before attempting to create the new LLM provider. If `create_llm()` raised a `ValueError`, the settings object was left in a partially mutated state. The fix: (1) validate that the Ollama model exists before touching settings, (2) snapshot the original settings values before mutating, (3) roll back the snapshot if `create_llm()` fails.

**Why (probable):** This bug is an instance of a general problem with shared mutable application state. FastAPI stores the LLM provider in `app.state`, which is a single shared object across all requests. A failed switch that leaves settings partially mutated means every subsequent request runs with incoherent configuration. The root cause was that the original code assumed `create_llm()` would succeed if the settings were valid, without recognizing that Ollama model availability is a runtime condition independent of settings validity. The rollback pattern (`prev_provider`, `prev_gemini_model`, `prev_ollama_model`) is the minimal transactional guarantee needed.

**Commits:** `e806d50`

---

### Security Hardening (Day One)

**What:** Several security-relevant changes were bundled in `e806d50`:
1. `FeedbackRequest.rating` changed from `str` to `Literal["up", "down"]` — prevents any arbitrary string reaching the database.
2. `DatabaseConnector.execute()` gained a `read_only: bool = False` parameter. When `True`, executes `PRAGMA query_only = ON` before running the SQL. The `/api/sql/execute` endpoint now passes `read_only=True`.
3. Tool error tracebacks removed from tool results — `json.dumps({"error": str(e), "traceback": ...})` became `json.dumps({"error": str(e)})`.
4. Protocol conformance assertions (`assert issubclass(ChromaVectorStore, VectorStoreBackend)`) added at import time.

**Why (probable):** Each addresses a distinct attack surface. The `Literal` constraint is the minimal input validation for an enum-typed field. The `read_only` SQL mode is defense-in-depth: while the analyst loop already enforces SELECT-only via prompt rules, the database layer should enforce the same constraint independently. `PRAGMA query_only = ON` causes SQLite to reject any write operation at the engine level, not just at the application level. Removing tracebacks addresses information disclosure: a Python traceback contains file paths, function names, and internal state that could help an attacker understand the system's structure.

**Commits:** `e806d50`

---

### Playwright for End-to-End Testing + MCP Integration

**What:** Playwright was added as the e2e testing framework (`@playwright/test` package, `playwright.config.ts`, initial two-test suite). `.mcp.json` was added to the repository root with a single server entry: `"playwright": { "command": "npx", "args": ["@playwright/mcp@latest"] }`. This configures Claude Code (via the MCP protocol) to use `@playwright/mcp` as a browser automation server, enabling the AI coding assistant to navigate, click, screenshot, and snapshot the running application directly during development sessions.

**Why (probable):** The choice of Playwright over Cypress comes down to three factors specific to this project. First, Playwright's `@playwright/mcp` package exposes a Playwright-controlled browser as an MCP server that Claude Code can drive directly for visual debugging — this is a unique integration that makes Playwright the natural choice when the development workflow involves an AI coding assistant that can issue browser commands. Second, Playwright has first-class support for Chromium, Firefox, and WebKit with a single API. Third, committing `.mcp.json` to the repository makes the Playwright browser tool available to any developer who opens the project in Claude Code — it is infrastructure for the development workflow, not just personal configuration.

**Commits:** `7d6d1a6`

---

### Spinner/Animation Completion States

**What:** Two bugs were fixed. `StatusChunk` always rendered a spinning `Loader2` icon regardless of whether the stream was complete, so every status message appeared to be in-progress even after the conversation had finished. The same issue existed in `ToolCallChunk`. Both components were updated to accept an `isComplete` prop. When `true`, the spinner or pulse is replaced with a green `CheckCircle` icon. The `isComplete` value is computed in `ChunkRenderer` from the chunk's position and the overall streaming state.

**Why (probable):** In a chat interface showing multiple agent steps (searching knowledge base → calling run_sql → executing SQL → generating answer), a spinner that never resolves implies the step is still running. A user watching a completed response sees a wall of spinning icons, which communicates "something is still happening" when everything has already finished. The `isComplete` prop is passed from the parent `ChunkRenderer` rather than computed inside the chunk component because the individual component cannot know whether the overall stream has ended — only the parent, which knows the full chunk list and streaming state, has that information.

**Commits:** `e0ae775`, `8c6eff2`

---

### Chart Type Expansion: Pie and Grouped Bar

**What:** Two new chart types were added. Pie charts: the heuristic detection threshold was relaxed from 6 to 10 rows, percentage labels and a legend were added. Grouped bar charts: a new `"grouped-bar"` chart type, detected when a query result has exactly two category columns plus one numeric column. A `pivotData()` utility reshapes the flat rows into a form where each category value becomes a separate `Bar` series with a distinct color. The color palette was expanded from 5 to 8 colors.

**Why (probable):** Two real evaluation questions drove these additions. First, questions about proportional breakdowns ("what percentage of transactions are UPI vs. NEFT vs. IMPS?") return a small number of distinct values and a pie chart is the natural representation. The 6-row limit was too restrictive. Second, cross-tabulation questions ("transaction count by age group and transaction type") produce two category columns, which the basic bar chart cannot handle — the result would require pivoting, which is exactly what `pivotData()` does. Individual bar coloring makes bar charts readable when there are many categories.

**Commits:** `984a2eb`

---

### Chart Awareness in the System Prompt

**What:** A new `## Visualization` section was added to `analyst_system.j2`. It tells the LLM three things: (1) charts are automatically rendered from query results, the LLM does not produce charts itself; (2) the specific data shape needed for each chart type (pie: 1 category + 1 numeric + 2–10 rows; grouped-bar: 2 category columns + 1 numeric; line: must include a temporal column); (3) an explicit instruction: "Never say 'I cannot create a chart.'" If the user asks for a chart of prior results, the LLM should re-run the query with the appropriate shape.

**Why (probable):** Without this context, the LLM had no knowledge of the frontend's chart detection logic. Two failure modes resulted: the LLM would apologize that it couldn't generate visualizations, and the LLM would not shape queries to produce chart-ready output. By giving the LLM the exact contract ("return 1 category + 1 numeric for pie"), the LLM can produce SQL that the detector will correctly identify. The "never say I cannot create a chart" instruction is a specific override of a strong default behavior in instruction-tuned models, which are trained to disclaim capabilities they lack.

**Commits:** `a26dcb7`

---

### SQL Persistence in Conversation History

**What:** The in-memory conversation store was enriched to include the SQL executed during each response. After the analyst loop completes, any SQL chunks are concatenated as a `[SQL: ...]` prefix on the assistant's history entry. The format stored in the in-memory history is: `[SQL: SELECT ...; SELECT ...]` followed by two newlines, then the final natural-language answer.

**Why (probable):** Multi-turn follow-up questions revealed a critical gap. When a user asks "show me this as a pie chart" after an earlier question, the LLM needs to know what SQL produced the previous results in order to re-run it with a different shape. Without the SQL in history, the in-memory context only contained the natural-language answer — the LLM would have to re-derive the query from scratch. Storing the SQL in the history entry bridges the context gap. The choice to prefix the SQL onto the existing assistant history string (rather than adding a separate `tool` message) is pragmatic: the in-memory store only models `user`/`assistant` roles, and a `[SQL: ...]` annotation is sufficient for the LLM to understand the prior query without requiring a schema change.

**Commits:** `a26dcb7`

---

### Table and Chart as Separate Inline Cards

**What:** The single combined tool result card was split into two independent rendered cards. The data table renders inside `ToolResultChunk`. The chart, if the data shape matches any chart type, renders as a separate animated card (`motion.div`) immediately below the table. The `DataTable` component gained an expand/collapse toggle: 10 rows by default, expanding to up to 100 rows.

**Why (probable):** The original combined card forced the table and chart to share a single container, which created layout tension: the chart had a fixed height, the table had variable rows, and together they made the card vertically long and visually heavy. Separating them into independent cards gives each a clean bounding box and allows them to be scanned independently — the user can read the table, then look at the chart, rather than parsing a single block. The separation also creates a natural visual rhythm: table (data) followed by chart (insight) mirrors how a human analyst would present findings. The 100-row cap on "expanded" view is a pragmatic upper bound — beyond 100 rows the table becomes unscrollable within the chat interface.

**Commits:** `741699a`

---

### Conversation Search

**What:** Full-text conversation search was added spanning backend and frontend. Backend: `PersistentConversationStore.search_conversations()` performs a two-pronged SQLite `ILIKE` search — one query finds conversations whose title matches, another finds all messages across all conversations whose content matches. Matching messages are grouped by conversation (max 3 snippets per conversation), with each snippet extracting ±40 characters around the match index. A new `GET /api/conversations/search?q=` endpoint returns up to 20 results, enforcing a minimum query length of 2. Frontend: a search toggle button in the sidebar reveals a controlled text input with 300ms debounce. While search is active, the conversation list is replaced with the `SearchResults` component.

**Why (probable):** A user who has run dozens of conversations needs a way to find a specific past analysis without scrolling. Server-side search (rather than client-side filtering) was chosen because the sidebar only loads conversation summaries, not the full message content — client-side search would require fetching all messages for all conversations first. The `ILIKE` approach is the minimal viable full-text search for SQLite: it requires no schema migration, no FTS5 configuration, and handles the query patterns expected. The 2-character minimum prevents expensive full-table scans on single-character queries. Capping at 3 snippets per conversation and 20 total results keeps the response payload small and the UI scannable.

**Commits:** `77a09ff`

---

# Phase 3: CI/CD, Firebase Deployment & Auth Hardening (Feb 14, Late)

## Overview

Phase 3 moved InsightXpert from a locally-runnable prototype to a publicly accessible, continuously-deployed production service. The core work was establishing a Firebase Hosting + Cloud Run split deployment behind a CI/CD pipeline driven by GitHub Actions with keyless GCP authentication. This phase also uncovered and fixed several production-only failure modes — a ChromaDB cold-start crash, an infinite React re-render that only manifested under real network latency, and TCP-coalesced SSE frames that collapsed the step-by-step streaming animation into a single flush.

---

## Decisions Made

### Firebase Hosting + Cloud Run Architecture (Static/Dynamic Split)

**What:** The Next.js frontend is compiled as a static export (`next build` with `output: 'export'`) and served from Firebase Hosting's global CDN. The FastAPI backend is containerized and deployed to Cloud Run. Firebase Hosting's `rewrites` configuration intercepts `/api/**` requests and routes them to the Cloud Run service, so from the browser's perspective everything is on the same origin — no CORS crossing for the production deployment.

```json
"rewrites": [
  { "source": "/api/**", "run": { "serviceId": "insightxpert-api", "region": "us-central1" } },
  { "source": "**", "destination": "/index.html" }
]
```

**Why (probable):** A single-deployment approach (e.g., running the Next.js dev server behind Cloud Run) would make the frontend a dynamic server-side render, forcing every page load to hit a container that may be cold. The static-export route means HTML/JS/CSS are served from Firebase's CDN in ~5ms globally, leaving Cloud Run to handle only authenticated API traffic. This is the right tradeoff for a competition context: the demo URL needs to load instantly for judges, and the AI query latency is unavoidable regardless of architecture.

**Commits:** `10ecbd5`, `b3bcb72`

---

### Workload Identity Federation Instead of Service Account Key Files

**What:** The initial commit used `credentials_json: ${{ secrets.GCP_SA_KEY }}` — a long-lived JSON service account key stored as a GitHub secret. Within 46 minutes this was replaced with Workload Identity Federation (WIF): GitHub's OIDC token, which is ephemeral and scoped to the specific workflow run, is exchanged for a short-lived GCP access token. No secret material is stored anywhere.

**Why (probable):** Service account key files are the most commonly exploited GCP credential type. They are long-lived (no automatic expiry), exportable, and if leaked through a compromised GitHub secret or a CI log they grant persistent access. WIF is the Google-recommended "keyless" alternative. The tradeoff is setup complexity (configuring the pool, provider, and SA binding in GCP IAM), but for a project that stores a live `SECRET_KEY` and `GEMINI_API_KEY` in the same GCP project, eliminating the SA key attack surface is worth the one-time setup cost.

**Commits:** `7a15981`

---

### GitHub Actions CI/CD Pipeline Design

**What:** Two workflows were created:
- `deploy.yml`: Triggers on push to `main`. Two sequential jobs: `deploy-backend` (build Docker image → push to GCR → `gcloud run deploy`) then `deploy-frontend` (npm build with `NEXT_OUTPUT=export` → `firebase-tools deploy --only hosting`). The frontend job has `needs: deploy-backend` so the live API is always updated before the new frontend goes live.
- `preview.yml`: Triggers on pull requests. Runs `test-backend` (uv + pytest) and `test-frontend` (npm lint + build) in parallel, then `preview-hosting` which deploys to a Firebase preview channel (`pr-{number}`) expiring in 7 days.

**Why (probable):** The sequential ordering of backend-before-frontend in the deploy pipeline prevents a window where the new frontend references an API endpoint or response field that the old backend doesn't serve yet. The PR preview channel design is well-suited for competition: reviewers get a live URL per PR automatically, so they can verify changes without pulling the branch locally.

**Commits:** `10ecbd5`, `7a15981`

---

### Firebase CLI Directly Instead of the Official GitHub Action

**What:** The initial pipeline used `FirebaseExtended/action-hosting-deploy@v0`, the official Firebase hosting deploy GitHub Action. This was replaced with a direct `npx firebase-tools` CLI call.

**Why:** `action-hosting-deploy@v0` was designed before WIF was standard practice. It expects to receive a JSON service account key blob and constructs credentials from it directly. When passed a WIF-derived service account email instead of a key blob, it fails to authenticate. The `firebase-tools` CLI, by contrast, respects Application Default Credentials (ADC) — the credentials already established by the `google-github-actions/auth` step. The WIF auth step writes a credentials file that ADC picks up automatically, so the CLI inherits authentication transparently.

**Commits:** `7fe5969`

---

### Cloud Run Memory Sizing and ONNX Model Pre-Caching

**What:** The default Cloud Run memory limit (512 MiB) was increased to 1 GiB, and ChromaDB's ONNX embedding model was pre-downloaded during Docker build rather than on first request:

```dockerfile
# Pre-download ChromaDB's ONNX embedding model so it doesn't download at runtime
RUN uv run python -c "import chromadb; chromadb.Client()"
```

**Why:** ChromaDB's default embedding function uses `sentence-transformers/all-MiniLM-L6-v2` serialized as an ONNX model (~79 MB). On a cold Cloud Run container start, this download happens inside the startup probe window. With 512 MiB memory, the Python process + FastAPI + ChromaDB + the in-flight 79 MB download together exceeded the limit, causing OOM kills that Cloud Run reported as startup failures. Pre-running `chromadb.Client()` during `docker build` bakes the model into the image layer. The runtime container starts with the model already on disk and only needs to load it into memory — a deterministic, fast operation.

**Commits:** `f5df02e`, `8745065`

---

### The `--cpu-boost` Flag and Cold Start Behaviour

**What:** Cloud Run's `--cpu-boost` flag allocates additional CPU to a container instance during startup until it becomes healthy, then scales CPU back to the configured allocation. Two commits (`868f5b6`, `1608a50`) fixed the same wrong flag name (`--startup-cpu-boost` is not a recognized flag; the correct flag is `--cpu-boost`) — documenting real trial-and-error against the live `gcloud` CLI.

**Why:** Cloud Run throttles CPU to the requested vCPU count the moment the container process starts. FastAPI with Uvicorn, ChromaDB loading its ONNX model, and the Vanna training routine are all CPU-intensive initialization steps. Running them at throttled CPU noticeably extends startup time — cold starts that might take 5 seconds at full CPU can take 15–20 seconds at the 0.08 vCPU that Cloud Run allocates to non-busy containers. For a competition demo with judges arriving at a URL that may have scaled to zero, a 20-second blank loading screen is a poor first impression.

**Commits:** `f5df02e`, `868f5b6`, `1608a50`

---

### Step-by-Step Streaming Architecture and the Agent Process Panel

**What:** The agent process panel is a sidebar component distinct from the chat message thread. It shows a live timeline of agent steps — RAG retrieval, LLM reasoning, SQL generation, tool execution, result rows — each as an expandable item with syntax-highlighted SQL, JSON-highlighted result data, the LLM's reasoning text, and copy buttons.

The streaming architecture is a three-layer pipeline:
1. **Backend:** `asyncio.sleep(0)` called after each `yield` to relinquish the event loop and force the ASGI server to flush that SSE frame before continuing.
2. **SSE client:** TCP can coalesce multiple SSE frames into one `reader.read()` call. A queue with 150ms staggered delivery (`CHUNK_STAGGER_MS = 150`) ensures each chunk animates as a discrete step.
3. **Hook:** `markLastRunningDone()` is called only on phase-transition chunks (`status`, `tool_call`, `tool_result`, `answer`, `error`) — not on `sql` chunks. This means the SQL detail merges into the running `tool_call` step rather than prematurely completing it.

**Why:** The process panel addresses a core UX problem in text-to-SQL interfaces: the "black box" period where the user sees a spinner but cannot know whether the agent is doing RAG retrieval, waiting for the LLM, running a slow query, or generating the chart. Making every phase visible turns a frustrating wait into a legible workflow. For a competition entry, this is also a demonstration signal — showing judges the RAG hits, the LLM's reasoning, the SQL it constructed, and the raw result rows is itself evidence of a well-instrumented system.

**Commits:** `2d809e7`, `65cb081`

---

### Population-Weighted Indian States Distribution

**What:** The synthetic dataset's `sender_state` column was previously drawn uniformly from 15 states. This was replaced with `random.choices(STATES, STATE_WEIGHT_VALUES)[0]` across all 36 states and union territories. Weights encode population × digital payment adoption (Maharashtra: 12.0, Karnataka: 8.0, Delhi: 7.0, ..., Lakshadweep: 0.02).

**Why:** A uniform distribution across states produces nonsensical analysis — query results showing Sikkim and Maharashtra contributing equally to transaction volume. The weighted distribution reflects two real-world signals: (1) state population, which determines the raw number of payment users, and (2) digital payment penetration. Completeness (all 36 states and UTs rather than a subset) also matters for queries like "which state had the fewest transactions?" — with a partial list, such queries produce misleading results.

**Commits:** `23c4277`

---

### AuthGuard Infinite Re-Render Loop

**What:** The `AuthGuard` component mounted with `checkAuth` in its `useEffect` dependency array. In Zustand, `checkAuth` is a function defined inside the store creator closure. On every store update (including the state changes triggered by `checkAuth` itself), Zustand creates a new store selector snapshot, causing `useAuthStore()` to return a new object reference. React sees a new `checkAuth` reference in the dependency array and re-runs the effect infinitely.

The fix uses a `useRef` guard to ensure `checkAuth` runs exactly once, and calls it via `useAuthStore.getState()` (a stable reference) rather than through the reactive hook.

**Why this was production-only:** Locally, the round-trip takes ~1ms and the loop completes before a human can notice. In production, Cloud Run adds 100–300ms latency per call. The loop iterates visibly at that cadence, holding `isLoading = true` indefinitely — a spinner that never resolves. **Lesson:** Any function extracted from a Zustand store via `useStore()` should not be placed in a `useEffect` dependency array unless the intent is to re-run the effect every time any store state changes. `getState().method()` is the correct pattern for imperative one-shot calls.

**Commits:** `23c30ca`

---

# Phase 4: Database Migration (SQLite → Turso) & Mobile UI (Feb 14-15)

## Overview

Phase 4 was a concentrated afternoon of fixes that bridged the gap between "works in development" and "works correctly in production." The session began with three cascading Firebase deployment failures that each exposed a different layer of the auth system. Once those were resolved, the two major structural changes landed: consolidating the previously-split auth and transactions databases into a single connection point, then replacing the ephemeral local SQLite file with Turso — a cloud-hosted libSQL service — to solve the fundamental statefulness problem of Cloud Run.

---

## Decisions Made

### Dynamic Secure Flag for Auth Cookies

**What:** The `Set-Cookie` response on `/api/auth/login` was hardcoded to `secure=False`. This was changed to detect the actual transport at request time: if `request.url.scheme == "https"` or the `X-Forwarded-Proto` header equals `"https"`, the cookie is set with `Secure=True`.

**Why (probable):** Chrome and Firefox silently drop `Set-Cookie` responses that omit `Secure` when the page is loaded over HTTPS — the cookie is received by the browser but immediately discarded, so it never appears in subsequent requests. The Cloud Run container itself terminates TLS at Google's edge and forwards plain HTTP internally, which is why `request.url.scheme` alone is insufficient and the `X-Forwarded-Proto` header (injected by the load balancer) must also be checked.

**Commits:** `a9d3742`

---

### Firebase Hosting `cleanUrls`

**What:** A single line was added to `firebase.json`: `"cleanUrls": true`.

**Why (probable):** Firebase Hosting serves a Next.js static export, which produces `login.html`, `index.html`, etc. as physical files. Without `cleanUrls`, a request to `/login` does not map to `login.html`; Firebase's routing falls through to the catch-all `**` rewrite rule, which serves `index.html`. The main `index.html` is the chat UI, which starts with an `AuthGuard` component. A user navigating directly to `/login` therefore saw the authenticated-only chat spinner briefly before being redirected. `cleanUrls: true` instructs Firebase to strip `.html` extensions and serve the corresponding file directly before the catch-all is ever evaluated.

**Commits:** `fa78030`

---

### Renaming the Auth Cookie to `__session`

**What:** The auth cookie was renamed from `access_token` to `__session` in both the place it is set and the place it is read.

**Why (probable):** Firebase Hosting rewrites (`/api/**` → Cloud Run) pass cookies through to the backend, but only cookies whose names appear on Firebase's allowlist. Firebase's documented behaviour is to forward only the `__session` cookie when proxying to Cloud Run services — all other cookies are stripped at the CDN edge. The `access_token` cookie was being correctly set by the browser, but the browser's subsequent requests to `/api/**` arrived at the FastAPI backend with no cookies at all, causing every protected endpoint to return 401. This constraint is specific to the Firebase Hosting → Cloud Run integration.

**Commits:** `b1f1e75`

---

### Consolidating Auth Tables into the Main Transactions Database

**What:** Until this commit, `main.py` created two separate SQLAlchemy engines: one from `settings.database_url` (the transactions database) and a second hardcoded to `sqlite:///./insightxpert_auth.db` for auth tables. After consolidation, there is a single `DatabaseConnector` instance, and the auth tables are created via `AuthBase.metadata.create_all(db.engine)` — reusing the same engine.

**Why (probable):** The split was originally convenient: the transactions database was treated as read-only analytical data, and keeping auth tables separate avoided any risk of DDL changes or auth writes touching the transactions schema. However, the separate file created an operational problem for Turso migration — managing two separate Turso databases (or a Turso database plus a local SQLite file on a Cloud Run container) reintroduces the ephemerality problem for one of them. Consolidation into a single `DATABASE_URL`-controlled connection means that replacing the URL with a Turso connection string in the next commit automatically covers both the analytical and auth layers.

**Commits:** `7e7aef1`

---

### Migrating from Local SQLite to Turso (Cloud-Hosted libSQL)

**What:** `settings.database_url` was switched from a local file path to a Turso cloud endpoint (`sqlite+libsql://insightxpert-nachiketkandari.aws-ap-south-1.turso.io?secure=true`). The `sqlalchemy-libsql` driver package was added. The `DatabaseConnector.connect()` method was updated to pass an `auth_token` to the SQLAlchemy `connect_args` when the URL contains `libsql`.

**Why (probable):** The root cause is Cloud Run's execution model. Cloud Run containers are stateless and ephemeral: each deployment replaces the previous container image, each scale-up event starts a fresh container from scratch with an empty writable layer, and each scale-to-zero event discards all in-memory and on-disk state. A local SQLite file written to the container's filesystem simply does not survive across deployments or container restarts. Every Cloud Run deployment wiped out all user accounts, conversation history, and message feedback.

Turso solves this by moving both databases to a cloud-hosted libSQL service. libSQL is a fork of SQLite that adds an HTTP/WebSocket transport layer while remaining fully SQLite-compatible at the SQL dialect level. From SQLAlchemy's perspective, the `sqlite+libsql://` URL scheme is handled by `sqlalchemy-libsql`, which translates standard SQLAlchemy operations into libSQL's HTTP API. The application code is otherwise identical. The `PRAGMA query_only = ON` guard was conditionally disabled for libSQL because the libSQL HTTP protocol does not support SQLite PRAGMAs.

**Commits:** `fc1fff2`, `08540d6`

---

### Mobile-First Responsive Design

**What:** A broad set of changes across 16 files made the chat interface usable on phone-sized viewports. Both sidebars became off-canvas `Sheet` components triggered by header buttons. Sidebar widths replaced with viewport-relative values: `w-[85vw] max-w-[320px]`. A `useEffect` in `app-shell.tsx` closes both sidebars when the viewport shrinks below the mobile threshold. The lazy initializer pattern was adopted for `useMediaQuery` to prevent SSR hydration mismatches. `layout.tsx` exported a `viewport` constant with `viewportFit: "cover"` for iOS notched iPhones. `globals.css` added `touch-action: manipulation` globally to disable the 300ms double-tap-to-zoom delay.

**Why (probable):** The Techfest IIT Bombay audience includes both desktop judges and mobile attendees. The original layout was completely broken on a phone, with both sidebars occupying the full viewport and no way to access them. The off-canvas sheet pattern is the standard mobile solution: panels are available on demand but don't consume screen real estate during the primary chat interaction.

**Commits:** `efb5166`

---

### CI Pytest Dependency Installation Fix

**What:** The GitHub Actions preview workflow ran `uv sync --frozen`, which installs only production dependencies. `pytest` and the test utilities live in the `dev` optional dependency group. The fix was `uv sync --frozen --extra dev`.

**Why (probable):** The missing `--extra dev` flag is a common uv pitfall: optional dependency groups must be explicitly requested at sync time. The fix reveals that backend tests were not being run in CI until this commit — the missing dependency would have caused the `uv run pytest` step to fail at the import stage, possibly being silently skipped.

**Commits:** `437cf55`

---

# Phase 5: UI Polish, Admin Panel & Real Data (Feb 14-18)

## Overview

Phase 5 ran across four days and covered a wide surface area: swapping synthetic data for a real UPI dataset, adding a multi-tenant admin system, introducing a second specialized agent for statistical rigour, redesigning the chat input to match contemporary AI-assistant conventions, and hardening the deployment for evaluation conditions. Many of the changes in this phase are directly motivated by the competition context — the Techfest IIT Bombay Leadership Analytics Challenge imposes constraints (evaluation windows, real data, demo judges) that drove several otherwise-unusual engineering choices.

---

## Decisions Made

### Replace Synthetic Data with Real UPI Transactions

**What:** The `generate_data.py` script was replaced by a CSV loader that reads `upi_transactions_2024.csv` and inserts verbatim. The dataset has a narrower but accurate schema: only SUCCESS and FAILED statuses (no PENDING), only 10 sender states, no NULL columns. The system prompt and the RAG documentation were updated to match these new constraints, and rules referencing NULL semantics were removed.

**Why (probable):** The competition challenge references "Leadership Analytics" over a dataset of Indian digital payment transactions. Submitting analysis on data the team itself generated would undermine the credibility of any insight — the judges are evaluating analytical quality, and a real dataset makes the answers verifiable and the patterns meaningful. The synthetic generator's NULL-handling logic in the system prompt was actively misleading the LLM, so removing it improved answer accuracy immediately. The seed script gained `INSERT OR IGNORE` and per-batch reconnection because Turso (libSQL) remote connections are flaky under sustained bulk inserts.

**Commits:** `991486b`, `e24b7ca`

---

### Admin Panel with Per-Org Feature Toggles, Branding, and User Mappings

**What:** A new `admin` module exposing seven API endpoints. Configuration is stored in a flat JSON file (`config/client-configs.json`) on the container filesystem. The data model has three layers: global defaults, organizations (`OrgConfig`), and user-to-org mappings. Each org carries a `FeatureToggles` object with six boolean flags and an `OrgBranding` object with `display_name`, `logo_url`, and a `theme` dict of CSS variable overrides. The frontend fetches `/api/client-config` on load, resolves the user's org, applies CSS variable overrides to `document.documentElement`, and gates features behind `isFeatureEnabled()` checks.

**Why (probable):** The "org" in this context is a competition judge or evaluator cohort, not a production customer. Feature gating allows the presenter to show a stripped-down interface to a non-technical judge while a technical reviewer can access everything. Branding overrides mean a single deployment can present as "HDFC Analytics" or "Paytm Insights" for different demo contexts by changing the JSON config without redeployment. The JSON file store, rather than a database table, was a deliberate choice: it avoids a schema migration for what is effectively a small configuration document, and is trivially editable by hand during a live demo without a database client.

**Commits:** `d152cc7`

---

### Second "Statistician" Agent

**What:** A new `statistician.py` agent added alongside the existing `analyst.py`. The orchestrator runs the analyst first, captures the last executed SQL and its result rows by intercepting streamed `"sql"` and `"tool_result"` chunks, then conditionally hands those rows to the statistician. The statistician has six tools: `run_python` (sandboxed Python with numpy, pandas, scipy.stats; `df` pre-bound to the analyst results), `run_sql` (for supplementary queries), `compute_descriptive_stats`, `test_hypothesis` (chi-squared, t-test, Mann-Whitney, ANOVA, z-proportion), `compute_correlation` (Pearson/Spearman/Kendall), and `fit_distribution`. The statistician's system prompt enforces formal statistical rigour: state null and alternative hypotheses, report p-values with effect sizes (Cohen's d, Cramer's V), apply Bonferroni correction for multiple comparisons, report 95% confidence intervals.

**Why (probable):** The competition is an analytics challenge, and a plain SQL answer ("the failure rate is 12.3%") would score lower than a statistically grounded answer ("the failure rate is 12.3%; a chi-squared test across transaction types yields χ²(3) = 847, p < 0.001, Cramer's V = 0.058, indicating a statistically significant but practically small association"). The analyst agent is optimised for SQL generation and cannot easily be prompted to also reason about distributional assumptions, hypothesis test selection, and effect size interpretation — these require a separate reasoning context. The two-agent pipeline avoids bloating the analyst's context window.

**Commits:** `d7ea23d`

---

### Gemini-Style Toolbar Redesign

**What:** The original message input was a horizontal flex container: a `<Textarea>` on the left and a single send/stop button on the right. This was replaced by a stacked layout: the `<Textarea>` on top, then below it an `InputToolbar` component containing a `+` dropdown menu on the left and a send/stop button on the right. The `+` menu holds Upload CSV (disabled placeholder), SQL Executor, and an Agents submenu with a Statistician toggle. The model selector was folded into the toolbar's right side. A gradient fade replaced the hard `border-t` line above the input.

**Why (probable):** The original design put actions users rarely need (model switching, SQL executor, agent toggling) in the header, which made the header cluttered, especially on mobile. Gemini's chat UI (and Claude's) move secondary actions into a `+` attachment-style menu attached to the input box, which is where the user's attention already is when composing a message. The gradient fade is cosmetically superior to a hard border on glassmorphism-styled interfaces because it suggests the conversation content continues behind the input rather than being cut off.

**Commits:** `d7ea23d`, `4882abb`

---

### Light/Dark Theme Architecture

**What:** The CSS variable layer in `globals.css` was restructured so `:root` defines the light theme (a warm cream/editorial palette: `oklch(0.96 0.005 75)` background) and `.dark` overrides it with the existing dark theme. A `use-theme.ts` hook reads `localStorage.getItem("theme")` on mount, defaults to `"dark"`, and exposes a `toggle()` function. RAG context titles are passed through a `data.rag_context` field on `"status"` chunks, giving the frontend a list of retrieved document names to display in the agent process sidebar.

**Why (probable):** The dark-only design worked well in a terminal-style demo context but looks jarring in a bright conference room or on a judge's laptop in a well-lit setting. The choice to store the preference in `localStorage` rather than a server-side user preference avoids a round-trip and a database column — appropriate for a competition project where persistence across devices is irrelevant. The RAG context display addresses a legitimate transparency concern: when the LLM retrieves past question-SQL pairs from ChromaDB, the user has no visibility into what prior knowledge is being applied. Displaying the retrieved document titles lets a judge understand why the system generated a particular SQL query.

**Commits:** `7cee270`

---

### Cloud Run Min-Instances 1 to Eliminate Cold Starts

**What:** Two flags were added to the `gcloud run deploy` invocation: `--min-instances 1` and `--max-instances 3`. Previously the service scaled to zero when idle.

**Why (probable):** Cloud Run's cold start on this container is significant — the container loads FastAPI with ChromaDB, SQLAlchemy runs `_migrate_schema()` and seeds the admin user, and imports scipy/numpy for the statistician agent — startup likely takes 10-30 seconds. In a competition evaluation context, a judge arriving at the demo URL after a period of inactivity and seeing a 20-second blank screen before the first response is a credibility-destroying first impression. A single always-warm instance costs approximately $10-20/month and eliminates this risk entirely. The cap at three instances prevents runaway costs if the demo URL gets unexpected traffic.

**Commits:** `1c66aab`

---

### Schema Changes: Inline Feedback, Starred Conversations, Last Active

**What:** Three schema changes bundled in one commit. (1) The standalone `feedback` table was dropped; two columns were added directly to the `messages` table: `feedback` (boolean, nullable) and `feedback_comment` (text, nullable). The "up"/"down" string was replaced with `bool | None` where None means no feedback given. (2) `is_starred` (boolean, default False) was added to `conversations`. (3) `last_active` (datetime, nullable) was added to `users`. Migration is performed by an idempotent `_migrate_schema()` function called at startup using raw `ALTER TABLE`, avoiding Alembic setup overhead.

**Why (probable):** The original `feedback` table required two write operations to record user sentiment. The inline approach reduces this to a single `UPDATE messages SET feedback = ?, feedback_comment = ? WHERE id = ?`, available in every message fetch without a join. The nullable boolean is cleaner than the "up"/"down" string enum (null = no feedback given, True = positive, False = negative). Starred conversations address the competition demo scenario where the presenter wants certain prepared conversations to appear first in the sidebar, pinned above others, regardless of recency. The no-Alembic approach is deliberate pragmatism: for three `ALTER TABLE` statements on a project with a short lifespan, hand-written idempotent SQL is faster and easier to reason about.

**Commits:** `6e60052`

---

### Cross-Origin Cookie SameSite for Vercel Deployment

**What:** The `set_cookie` call was made conditional on whether the request `Origin` header differs from the backend's own hostname. When the origins differ — i.e., the frontend is on `*.vercel.app` and the backend is on `*.run.app` — the cookie is set with `SameSite=None`. When they match (same-origin, local development), it stays `SameSite=Lax`.

**Why (probable):** The deployment topology has the frontend on Vercel and the backend on Cloud Run. These are different registrable domains, so the browser's SameSite policy blocks `SameSite=Lax` cookies from being sent on cross-site requests. Setting `SameSite=None` is the correct fix but requires `Secure=True`, which is enforced by the existing `is_https` check. The conditional avoids breaking local development where `SameSite=None; Secure` on `http://localhost` would itself cause the cookie to be blocked.

**Commits:** `455a36c`

---

### gcloud `--set-env-vars` URL Parsing Bug

**What:** The `CORS_ORIGINS` value contains a literal comma (two URLs). This caused `gcloud` to misparse the argument, splitting `CORS_ORIGINS` at the comma and treating the second URL as a new (malformed) key-value pair. The fix uses gcloud's alternate delimiter syntax: `^||^` prefixes the string to declare `||` as the delimiter, and all variable separators are replaced with `||`.

**Why (probable):** This is a pure shell escaping bug that only manifests with values that contain the delimiter character. The `CORS_ORIGINS` variable is the only one that contains a comma in its value, and it was not discovered until the Vercel domain was added to the allowlist (making the value a comma-containing string for the first time). The `^||^` syntax is documented in `gcloud topic escaping` but not prominently. **General principle:** any environment variable passed via a delimited CLI flag is a potential injection point if the value contains the delimiter.

**Commits:** `67a3f6e`, `eb914d1`

---

# Phase 6: Streaming Hardening, Benchmarks, Security & Phase 0 Cleanup (Feb 17-26)

## Overview

Phase 6 spans ten days and forty commits. The work falls into four distinct arcs:

1. **Streaming hardening** (Feb 17–18): A cluster of bugs in the SSE pipeline — Firebase proxy buffering, conversation persistence ordering, per-conversation streaming state, chunk routing, and the `isComplete` prop threading — each independently broke the streaming experience.
2. **Benchmark infrastructure and correctness** (Feb 18): The benchmark runner was made scientifically fair by fixing forced-tool-use enforcement, adding RAG isolation between questions, and filtering out low-quality or invalid SQL from retrieval context.
3. **Admin panel expansion and security hardening** (Feb 25–26): Dynamic runtime-editable prompt templates, admin conversation viewer, and a sequence of security fixes addressing credential leakage in logs, SSTI in the prompt renderer, and path traversal in the file reader.
4. **Phase 0 pre-launch hardening** (Feb 26): A named philosophical milestone — cross-cutting cleanup that replaced bare excepts with a typed exception hierarchy, added 20 integration tests across four categories, and introduced the clarifier agent.

---

## Decisions Made

### Firebase Hosting Cannot Proxy SSE: Use Cloud Run URL Directly

**What:** The frontend's SSE chat endpoint was being called through Firebase Hosting rewrites. Firebase Hosting's CDN layer buffers the entire HTTP response body before forwarding it to the browser. For an SSE stream, this meant the client received all chunks at once at the end, functionally identical to a non-streaming response. The fix was to fetch the Cloud Run service URL at CI build time using `gcloud run services describe` and inject it as the `NEXT_PUBLIC_API_URL` environment variable baked into the Next.js static export. The frontend then calls Cloud Run directly for the SSE endpoint, entirely bypassing Firebase Hosting for that request.

**Why (probable):** Firebase Hosting is a CDN and static asset host. Its rewrite/proxy feature is designed for JSON APIs and page routes, not long-lived streaming connections. The CDN infrastructure buffers responses for caching and compression. This is not a Firebase bug — it is the expected behavior of any HTTP reverse proxy that isn't explicitly configured for streaming pass-through. Since Firebase Hosting does not expose that configuration, the only correct solution is to bypass it. The trade-off is that the Cloud Run service URL must be public and that CORS must be configured correctly on the backend.

**Commits:** `3103fb1`

---

### Conversation Persistence Must Complete Before the SSE Sentinel

**What:** The `[DONE]` sentinel was yielded before the `await persist_response()` call completed. If a client disconnected immediately after receiving `[DONE]` (which SSE clients often do), the persistence coroutine was cancelled and the assistant message was never saved. The fix moved persistence before `yield {"data": "[DONE]"}`, and added a hydration path that re-populates the in-memory store from the persistent store when the in-memory history is empty.

**Why (probable):** The original ordering matched the intuitive "finish streaming, then save" mental model. The subtlety is that in async generator-based SSE, the client-disconnect event cancels the generator's execution. Anything after the final `yield` in the happy path is at risk if the client is fast. The restart/TTL gap was a straightforward oversight: the in-memory store was treated as a write-through cache but was never read back from its backing store.

**Commits:** `f4639db`

---

### `isComplete` Prop Should Not Apply Universally to All Chunk Types

**What:** The inline progress steps feature introduced a prop `isComplete: boolean` on `ChunkRenderer`. A subsequent commit passed `isComplete={i < message.chunks.length - 1 || !isStreaming}` uniformly to every chunk, setting `isComplete=true` on chart and table chunks the moment they were no longer the last chunk in the list. Because charts arrive before the answer chunk, they were immediately marked complete, collapsing the animation. The fix scoped `isComplete` to only `status`, `tool_call`, and `answer` chunks. Chart and visualization chunks were decoupled: their `ProgressStep` uses an internal 600ms timer to transition from spinner to checkmark, independent of streaming state.

**Why (probable):** The `isComplete` prop was added in one commit and then universally threaded through message rendering in a following commit without accounting for the semantics of each chunk type. The internal timer decoupling is the principled fix: the chart-rendering step should reflect time-to-render, not position-in-stream.

**Commits:** `064125c`, `b9f2e17`

---

### Forced Tool Use Guard in the Analyst Loop

**What:** Gemini and smaller models would occasionally answer data questions directly from RAG context without calling `run_sql`. The fix adds a `tools_executed` flag in the analyst loop. If the LLM produces a final response (no tool calls) on any iteration before any tool has been called, the loop reinjects a correction message: `"You MUST use the run_sql tool to query the database before answering."` and continues to the next iteration rather than returning the answer.

**Why (probable):** This matters most for benchmark fairness. When measuring model accuracy on the 250K transaction dataset, a model that answers from RAG-retrieved SQL examples without actually executing the SQL appears to succeed even though it is not querying the live data. The answer may be correct (if the RAG example matches the question exactly) but the measurement is meaningless — it tests RAG retrieval quality, not the model's SQL generation capability.

**Commits:** `f77f22c`

---

### RAG Quality: Similarity Threshold, Validity Metadata, and Benchmark Isolation

**What:** Three related problems were fixed simultaneously. (1) A `max_distance=1.0` filter was added to `search_qa()` to prevent retrieval of semantically distant QA pairs. (2) All curated training pairs and auto-saved pairs now carry `sql_valid=True` metadata. ChromaDB's `where` clause filters on this metadata at query time. (3) For benchmark runs, the benchmark now calls `flush_qa_pairs()` between questions — which drops and recreates the `qa_pairs` ChromaDB collection — then re-seeds from the curated training set only. Additionally, the DDL and documentation RAG searches were eliminated from the analyst loop (these were redundant since DDL and docs are already injected directly into the system prompt).

**Why (probable):** RAG retrieval is a multiplier on LLM quality — bad retrievals actively harm performance by filling the context window with irrelevant or broken examples. The `sql_valid` flag is a stronger signal than similarity alone. Benchmark isolation is a fundamental methodology requirement: each model-question pair must start from the same state, otherwise measured accuracy is confounded by what questions came before.

**Commits:** `a538a6f`

---

### 147 Sample Questions Modal: Making the Corpus Discoverable

**What:** A browsable modal accessible from the user menu exposes 147 pre-written questions organized into 11 categories: Descriptive/Summary Statistics, Comparative Analysis, Temporal/Time-Series, Segmentation/Group Analysis, Correlation/Relationship, Risk/Fraud Analysis, Multi-Dimensional/Pivot, Edge Cases/Boundary, Complex/Advanced, Intentional Traps, and Stress Test/Large Result Set. The modal includes live search filtering, sticky category headers, and click-to-insert into the chat input.

**Why (probable):** A text-to-SQL system whose capabilities are invisible to the user will be underutilized. The 147 questions serve two purposes: they demonstrate the breadth of what the system can answer, and they include a deliberately adversarial "Intentional Traps" category with questions about concepts not in the dataset (revenue, profit margins, inventory) to demonstrate graceful refusal. The 11-category structure mirrors the Techfest IIT Bombay evaluation rubric, making it a practical study guide for contest participants.

**Commits:** `a414c33`

---

### Dynamic Runtime-Editable Prompt Templates

**What:** Phase 2 introduced Jinja2 `.j2` template files for system prompts — these were compiled-in and required a container rebuild to change. Phase 6 introduced a `PromptTemplate` database model and a DB-first rendering pipeline. The `render()` function accepts an optional `engine` parameter. When provided, it queries the `prompt_templates` table for a template matching the prompt name (with `is_active=True`). If found, it renders the DB content using Jinja2. If not found, it falls back to the `.j2` file. On first startup, the server seeds the database from the `.j2` files. The admin panel exposes CRUD endpoints with a full editor UI.

**Why (probable):** Contest deployments need rapid iteration on prompt wording without CI/CD cycles. A file edit triggers a 5-minute deploy pipeline. With the DB-backed system, an admin can edit and save the prompt in the browser and the next request uses the new version. The file fallback is essential for cold starts and disaster recovery: if the database is unavailable or the admin accidentally blanks a prompt, the system degrades to the known-good file-based defaults rather than failing completely.

**Commits:** `e5f7488`, `de1a70d`, `35c0878`

---

### Path Traversal in the Prompt File Reader

**What:** `get_file_content(template_name)` did `path = _PROMPTS_DIR / template_name` and `path.read_text()` with no validation. A `template_name` value of `../../etc/passwd` would resolve to an arbitrary file outside the prompts directory. The fix calls `.resolve()` on the constructed path and checks `path.is_relative_to(_PROMPTS_DIR.resolve())` before reading.

**Why (probable):** The `{name}` path parameter was the sole input. Even with the regex constraint on the path parameter (added in the same security commit wave), the defense-in-depth principle requires the file reader itself to validate the resolved path independently, since the function could in theory be called from other contexts.

**Commits:** `de1a70d`

---

### SSTI in the DB-Backed Prompt Renderer

**What:** The initial implementation used the standard `jinja2.Environment` to render DB-sourced template content. A standard Jinja2 environment allows template code to access `config`, walk `__class__.__mro__`, and in some configurations execute shell commands. Since the `content` field of `PromptTemplate` is admin-editable, any admin user could inject a payload and exfiltrate server-side secrets. The fix switches DB-sourced content to `jinja2.sandbox.SandboxedEnvironment`, which restricts attribute access and blocks access to Python internals. File-based templates continue to use the regular environment.

**Why (probable):** File-based templates are treated as trusted code (they ship with the application). DB-sourced templates are treated as untrusted user input (they can be modified by any admin account). The fact that the regular environment was used initially suggests the SSTI risk was not considered when the DB rendering path was added — the two-environment approach reflects the principle of treating runtime-editable content as adversarial even from authenticated internal users.

**Commits:** `35c0878`

---

### Credential Logging: Database URLs in Plaintext

**What:** In two places, the fully-constructed database URL was passed directly to logger calls. For PostgreSQL, MySQL, or Turso (libSQL), the URL includes the password in plaintext: `postgresql://user:password@host/db`. These lines would write the password to any log aggregation service in plaintext, visible to anyone with log read access. The fix uses SQLAlchemy's `engine.url.render_as_string(hide_password=True)` which replaces the password component with `***`.

**Why (probable):** This is the most critical security fix in Phase 6. Log aggregation is typically less access-controlled than secret management systems. The fact that it was missed initially is a common pattern: database URL logging is added for debugging purposes when the application only supports SQLite (which has no password), and then the logging line survives unchanged when production databases with credentials are added later.

**Commits:** `35c0878`

---

### Admin Conversation Viewer: Replaying User Sessions

**What:** The admin panel gained a full conversation replay feature. Two new backend endpoints: `GET /api/admin/users/{user_id}/conversations` (lists all conversations for a user) and `GET /api/admin/conversations/{conversation_id}` (fetches full conversation data without the ownership check). The frontend renders conversations through the same `ChunkRenderer` components used in the chat UI, meaning SQL blocks, data tables, and charts render in the viewer exactly as they appeared to the user. The viewer is a modal with circular prev/next navigation through a user's conversation list.

**Why (probable):** For a contest setting, the ability to audit what questions participants asked and how the system responded is operationally necessary. If a benchmark score seems anomalous, the admin can inspect the actual LLM outputs. The decision to reuse existing `ChunkRenderer` components rather than building a separate read-only renderer was deliberate: it means the viewer always stays in sync with any future chunk type additions, and there is no duplicated rendering logic to maintain.

**Commits:** `d777234`, `e0d3c2a`, `0666a0f`, `445ac78`, `26e931a`, `6bf2d72`

---

### Numeric Rounding: Data Fidelity for Analytics

**What:** The analyst system prompt previously contained the instruction `ROUND() all decimal results to 2 decimal places`. This was changed to `Do NOT round numeric values unless the user explicitly asks for rounding`.

**Why (probable):** Two-decimal rounding is appropriate for currency display but actively harmful for analytics. A fraud rate of `0.00347` rounded to `0.00` is useless. A Pearson correlation of `0.8234` rounded to `0.82` loses precision. The original rule likely came from the idea that monetary amounts should be formatted for readability. However, the dataset contains calculated metrics (rates, averages, percentages, correlations) where precision matters. The fix shifts the responsibility to the user: if they want rounded results, they can ask explicitly.

**Commits:** `4c3bd3a`

---

### Clarifier Agent: Pre-Check Before the Full Analyst Loop

**What:** A new `clarifier.py` module implements a lightweight pre-check before the analyst loop runs. It makes a single non-streaming LLM call asking the model to classify the user's question as either `{"action": "execute"}` (proceed) or `{"action": "clarify", "question": "..."}` (ask for more information). The check is intentionally conservative and includes the last four messages of conversation history. On any parse failure or LLM error, it defaults to `execute`.

**Why (probable):** The full analyst loop involves at least one LLM call plus a SQL execution round-trip, taking several seconds. A clarification request from the analyst loop arrives after that latency and mid-stream, creating a disruptive experience. The pre-check is fast (no tools, no SQL, no streaming) and fires before any work starts. The fail-open design (`default to execute`) is intentional: a false positive clarification request (asking for clarification on an unambiguous question) is more harmful to UX than a false negative (proceeding on a mildly ambiguous question that the analyst can handle contextually).

**Commits:** `acd3d9a`

---

### Phase 0: Pre-Launch Hardening Philosophy

**What:** The "Phase 0" label was applied to a commit (`acd3d9a`) that touched 21 files and added 1,523 lines. Its scope: a custom exception hierarchy (`InsightXpertError` base with `DatabaseError`, `QuerySyntaxError`, `QueryTimeoutError`, `DatabaseConnectionError`, `ValidationError`, `NotFoundError`, `LLMError`, `ServiceUnavailableError`), global FastAPI exception handlers that convert these to consistent JSON envelopes (`{"error": "...", "code": "..."}`), 20 new integration tests, and inline documentation across 7 core files.

**Why (probable):** "Phase 0" is a pre-launch hardening pass — make the product safe to put in front of real users. The application had been developed with product features as the priority; the exception handling was a patchwork of `except Exception: pass` blocks and ad-hoc logging. Before exposing the system to contest participants, the error surface needed to be predictable: every unhandled error should return a structured JSON response with a stable `code` field, not a raw Python traceback or an empty 500. The integration tests locked in the behavior of the full request pipeline before the final deployment freeze.

**Commits:** `acd3d9a`, `fe46686`

---

### DetachedInstanceError: SQLAlchemy Session Lifecycle

**What:** The auth dependency function `get_current_user` opens a SQLAlchemy session, updates `user.last_active`, commits, calls `session.expunge(user)` to detach the ORM object, and returns the user. The `DetachedInstanceError` occurred when code outside the session tried to access a lazy-loaded attribute on the detached user object. The fix adds `session.refresh(user)` before `session.expunge(user)`, eagerly loading all mapped attributes into the Python object's `__dict__`.

**Why (probable):** The `User` model has attributes that SQLAlchemy may not have loaded during the initial query. The `refresh()` call issues a `SELECT * FROM users WHERE id = ?` to fully populate the object before it is detached. This is the canonical SQLAlchemy pattern for passing ORM objects outside the session lifecycle.

**Commits:** `54f10c4`

---

### `generate_data.py` Table Preservation on Data Reload

**What:** The synthetic data generation script previously deleted the entire `insightxpert.db` file before recreating it. This meant that running `python generate_data.py` would destroy all auth tables: `users`, `conversations`, `messages`, `prompt_templates`. The fix drops and recreates only the `transactions` table, leaving all other tables intact.

**Why (probable):** During development, it is common to regenerate synthetic data to test different distributions or row counts. Before this fix, every data reload would log out all users and destroy all test conversations. The fix is minimal and correct: `DROP TABLE IF EXISTS transactions` followed by `CREATE TABLE transactions`. SQLite does not require a full file delete to achieve a clean table.

**Commits:** `545e1b6`

---

### Cloud Run Deployment: Turso Connection and Startup Timing

**What:** Three separate Cloud Run deployment issues were fixed. (1) The `libsql://` URL scheme produced by the Turso console is not a valid SQLAlchemy dialect string. The connector was updated to rewrite `libsql://host` to `sqlite+libsql://host?secure=true`. (2) SQLite `PRAGMA` statements were being sent to remote Turso connections, which uses an HTTP API that rejects PRAGMA statements with a 405. The connector now skips PRAGMAs when `_is_libsql_remote=True`. (3) ChromaDB's ONNX embedding model was downloading and compiling at container startup, causing Cloud Run health probe timeouts. RAG training was moved to a background `asyncio.to_thread` task with a 120-second timeout, allowing the server to begin accepting requests immediately. A `/health` endpoint was added for Cloud Run startup probes.

**Why (probable):** Each of these was a cold-deploy failure that would only manifest on Cloud Run, not in local development (which uses local SQLite, no PRAGMA issues, and pre-cached ONNX models). The URL scheme mismatch is a documentation/convention gap between Turso's tooling and SQLAlchemy's dialect naming. The PRAGMA issue is a consequence of the remote HTTP protocol not implementing the SQLite wire protocol.

**Commits:** `47e9a68`

---

## Final State of the Project

**Architecture at end of Phase 6:**

- **Backend**: FastAPI (Python) running on Cloud Run. Single process: one SQLAlchemy engine connected to either local SQLite or remote Turso (libSQL). One ChromaDB instance (local ONNX embeddings, four collections: `qa_pairs`, `ddl`, `docs`, `findings`). Gemini (primary) or Ollama (benchmark/local) as the LLM.

- **Agent pipeline**: `orchestrator_loop` dispatches to `clarification_check` (fast pre-call), then `analyst_loop` (SQL generation + execution + chart suggestion), and optionally to `statistician_loop` (scipy/numpy sandboxed statistical analysis).

- **Prompt rendering**: DB-first (Jinja2 `SandboxedEnvironment` for DB content, regular `Environment` for files), with file-based `.j2` fallback. Admin-editable at runtime without redeployment.

- **RAG**: Four ChromaDB collections. `qa_pairs` filtered by `sql_valid=True` and `max_distance=1.0` at retrieval time. DDL and docs injected directly into system prompt, not retrieved. Auto-saved pairs tagged `sql_valid=True` after successful execution.

- **Frontend**: Next.js static export on Firebase Hosting. SSE calls go directly to Cloud Run (bypassing Firebase proxy). Zustand for state. 147-question sample modal, admin conversation viewer, time-grouped sidebar, collapsible charts, light/dark theme.

- **Security**: httpOnly `__session` JWT cookies, CORS origin allowlist, read-only SQL enforcement (guard in analyst loop + `PRAGMA query_only`), `SandboxedEnvironment` for admin-edited prompts, path traversal prevention in file reader, regex-validated prompt name path parameters, `render_as_string(hide_password=True)` on all database URL log statements.

- **Testing**: Pre-existing unit tests (RAG, DB, auth) plus 20 Phase 0 integration tests covering orchestrator pipeline, API contract, conversation persistence, and error scenarios. Benchmark runner (`benchmark/runner.py`) for multi-model comparison with isolated RAG state per model.

- **Deployment**: GitHub Actions with Workload Identity Federation (WIF). Backend to Cloud Run (1Gi memory, `min-instances=1`, HTTP startup probe on `/health`). Frontend static export to Firebase Hosting with `NEXT_PUBLIC_API_URL` baked in at build time. ONNX embedding model warmed during Docker build.
