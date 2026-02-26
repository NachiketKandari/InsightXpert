# InsightXpert: Unified Progress Report

> **Generated:** Feb 26, 2026 — 2 days before submission deadline (Feb 28)
> **Branch:** `clarification-and-datasets` (pending merge to main)
> **Commit count:** ~100 across 6 phases

---

## 1. What We Set Out to Build

### The Techfest Brief
An AI data analyst for the IIT Bombay Leadership Analytics Challenge — a conversational system letting non-technical leadership (product managers, operations heads, risk officers) ask plain-English questions over 250K synthetic Indian digital payment transactions and receive accurate, well-explained insights.

**Evaluation rubric weights:**
- Insight Accuracy: 30%
- Explainability: 20%
- Conversational Quality: 15%
- Technical Implementation: 15%
- Scalability/Performance: 10%
- Innovation: 10%

### The Extended Roadmap (AI conversation, Feb 25)
After establishing the core product, a 6-phase feature roadmap was planned:

| Phase | What | Complexity |
|-------|------|------------|
| 0 | Code cleanup + integration tests | 1 week |
| 1 | DDL/prompts in DB + clarification flow | 1.5 weeks |
| 2 | 👍 feed semantic search, admin column editor, user monitoring | 1 week |
| 3 | CSV upload with auto DDL extraction + model benchmarking | 2 weeks |
| 4 | Tool call expansion (50 tools, smart routing) + statistical analysis | 2 weeks |
| 5 | Workflows + email notifications | 2 weeks |
| 6 | Discovery agent (autonomous monitoring + alerts) | 1.5 weeks |

---

## 2. Where We Are Now

**Current state:** A production-deployed full-stack AI analyst platform. Backend on Cloud Run, frontend on Firebase Hosting, CI/CD fully wired. The core agent loop is robust, tested, and production-stable. The most recently completed work (current branch) adds a clarification pre-check, a full datasets management system, and a two-phase analyst→statistician orchestrator.

**Codebase statistics:**
- Backend Python: ~7,000 LOC across 30+ modules
- Backend tests: ~3,260 LOC across 16 test files
- Frontend: ~4,000 LOC, 50+ components
- Docs: ARCHITECTURE.md (72KB), project-decisions.md (91KB), WALKTHROUGH.md

---

## 3. What Is Done

### Phase 0: Code Cleanup ✅ Complete
- Dead code removed; all if/elif tool dispatch chains replaced with registry pattern
- LLM Factory, Tool ABC + Registry, VectorStore Protocol all extracted
- Jinja2 prompt templates extracted from code
- Settings mutation bug on LLM switch fixed (rollback on failure)
- Error-as-data philosophy throughout SSE generator
- SSTI-hardened sandboxed Jinja2 for user-editable prompts
- Path traversal fix for prompt file reader
- Integration test suite with MockLLM, in-memory SQLite, FastAPI test client
- 16 test files, ~3,260 LOC

### Phase 1a: Prompts & DDL Live in DB ✅ Complete
- `PromptTemplate` SQLAlchemy model in auth DB
- `prompts/__init__.py` uses DB-first, file-fallback strategy
- Admin UI: full prompt template CRUD (list, edit, reset to default, delete)
- `Dataset`, `DatasetColumn`, `ExampleQuery` models with cascade deletes
- `DatasetService`: CRUD, activation (one active at a time), markdown generation from column metadata
- Admin API endpoints at `/api/datasets/*` (9 endpoints, admin-only)
- Orchestrator reads active dataset DDL/docs at runtime, falls back to hardcoded training data
- Idempotent seeding: 17 columns + 12 example queries bootstrapped on first startup
- `training/trainer.py` can train RAG from DB dataset or hardcoded defaults

### Phase 1b: Clarification Flow ✅ Complete
- `agents/clarifier.py`: lightweight pre-check LLM call before full analysis
- System prompt + schema + question → JSON `{action: "execute"|"clarify", question?: "..."}`
- Strips markdown fences from JSON response, falls back to "execute" on any error
- Includes last 4 conversation messages for context
- Orchestrator gates analyst loop behind clarifier result
- Frontend: `clarification-chunk.tsx` renders clarifying question in amber card
- "Just answer with best guess" skip button wires `skip_clarification: true` to backend
- SSE client passes skip flag; backend bypasses clarifier if set
- Full test coverage: 7 test cases covering clear questions, ambiguity, JSON errors, history inclusion

### Phase 2b: Admin UI for Column Descriptions ✅ Complete
- Datasets admin panel with full column editor (name, type, description, domain values, domain rules)
- Example query management per dataset (add, delete)
- Dataset activation toggle
- "Retrain RAG" action from active dataset

### Phase 2c: User Monitoring ✅ Complete
- Admin Conversations tab: user list with per-user stats (# conversations, # messages, last active)
- Expandable rows showing each user's conversations
- Full conversation viewer modal: paginated prev/next navigation, chunk-by-chunk replay, feedback indicators
- Delete individual conversations or all conversations for a user
- Admin can see all users' conversations, regular users see only their own

### Core Pipeline ✅ Complete (established in Phases 1-2 of original development)
- 5-step analyst loop: RAG retrieval → prompt assembly → agentic tool-calling iteration → guard rail → auto-save
- Tools: `RunSqlTool` (read-only enforced), `GetSchemaTool`, `SearchSimilarTool`
- Two-phase orchestrator: analyst always runs; statistician runs conditionally on results + agent_mode
- Statistician agent with `ExecutePythonTool` and `TestHypothesisTool` for statistical inference
- ChromaDB RAG: 4 collections (qa_pairs, ddl, docs, findings), SHA256 deduplication, idempotent trainer
- Multi-LLM: Gemini 2.5 Flash (default) + Ollama (local fallback), runtime switching with rollback
- JWT + bcrypt auth with httpOnly cookies, admin flag, domain-based admin detection
- Dual conversation store: in-memory LRU (for LLM context) + persistent SQLite (for history replay)
- SSE streaming with typed ChatChunk protocol (status, tool_call, sql, tool_result, answer, error, clarification)
- Multi-org support: per-org feature toggles, branding (CSS variables), admin domain whitelist
- CI/CD: GitHub Actions preview pipeline (backend tests + frontend lint/build) + production deploy (Cloud Run + Firebase)
- Frontend health check: polls `/health`, shows static 503 page on backend failure
- Frontend: chat UI, left sidebar (history + search), right sidebar (agent step timeline), admin panel, SQL executor, dataset viewer

---

## 4. What Is Left

### Phase 2a: 👍 Reactions Feed Semantic Search ❌ Not Done
**What was planned:** When a message gets thumbs-up, flag it in messages table; update semantic search retrieval to boost/include thumbs-up examples.

**Current state:** Feedback is stored in `MessageRecord.feedback` (bool) and `feedback_comment` (str). The `/api/feedback` endpoint writes it to DB. But the RAG retrieval in `analyst.py` does not read feedback — it only queries `qa_pairs` by cosine similarity. The auto-save of successful Q→SQL pairs ignores feedback signals entirely.

**Gap:** The bridge between `MessageRecord.feedback=True` and ChromaDB retrieval boost does not exist. Implementing it would require: on thumbs-up, upsert the question+SQL pair into `qa_pairs` with a metadata flag (e.g., `user_approved: True`), then in RAG retrieval, weight or prioritize docs with that flag.

---

### Phase 3a: CSV Upload with Auto DDL Extraction ❌ Not Done
**What was planned:** Upload endpoint accepts CSV → LLM reads first 3 rows → generates DDL + column descriptions + confidence scores → asks user about low-confidence columns → creates SQLite table → populates dataset in DB.

**Current state:** The `Dataset`, `DatasetColumn`, and `ExampleQuery` models exist and the admin panel can edit them manually. But there is no upload endpoint, no LLM DDL inference, no CSV-to-SQLite table creation, and no confidence-gated clarification during upload.

**Dependency satisfied:** Dataset model is in place — this just needs the upload + inference layer.

---

### Phase 3b: Model Benchmarking ❌ Not Done
**What was planned:** `benchmarks` table storing query, expected SQL, model used, latency, correctness score. Run the question bank against multiple models; compare in a dashboard.

**Current state:** Nothing exists. No benchmarks table, no evaluation runner, no comparison dashboard.

**Note:** The PRD question bank (147 questions across 7 files) is the ready-made benchmark suite.

---

### Phase 4a: Tool Call Expansion with Smart Routing ❌ Not Done
**What was planned:** 50 tools organized into categories; a lightweight router LLM call selects which 4-6 tools to inject per query; two-stage architecture: route → execute.

**Current state:** 3 analyst tools (`RunSql`, `GetSchema`, `SearchSimilar`) + 2 statistician tools (`ExecutePython`, `TestHypothesis`). No tool router, no category system, no dynamic context injection.

---

### Phase 4b: Statistical Analysis Upgrade ⚠️ Partial
**What was planned:** Correlation analysis, outlier detection, distribution fitting, trend decomposition, significance testing — all as tool calls.

**Current state:** `agents/statistician.py` exists with `ExecutePythonTool` and `TestHypothesisTool`. Tests cover trends, outliers, correlations, statistical summaries. However the statistician is described as "skeleton in place, minimal tool execution" — the depth of statistical analysis is limited.

---

### Phase 5: Workflows + Email Notifications ❌ Not Done
**What was planned:** Saved query sequences, manual + scheduled triggers (APScheduler/Celery beat), email results with charts, workflow builder UI.

**Current state:** Nothing exists. No workflow model, no scheduler, no email integration.

---

### Phase 6: Discovery Agent ❌ Not Done
**What was planned:** Autonomous agent that scans conversations/workflows, ranks metrics by importance, auto-creates monitoring jobs, runs SQL on schedule, LLM-analyzes threshold breaches, sends email alerts.

**Current state:** The `findings` ChromaDB collection is pre-registered but has never been populated. No discovery agent, no scheduler, no alerting.

---

## 5. Reprioritized Roadmap

Given that **submission is Feb 28 (2 days away)** and the **demo/presentation is Mar 8**, the priority order shifts dramatically:

### Immediate (Today, Feb 26 — before submission)

**P0: Merge clarification-and-datasets to main**
- Current branch has 2,353 insertions, all tests passing, CI should be green
- This is the single most important action — get the working code into production

**P1: Run the question bank**
- Fire all questions from `prd/QuestionBank/` against the running system
- Identify any queries that produce wrong SQL, chart errors, or crashes
- Fix regressions; do not add features

**P2: Phase 2a — Thumbs-up feeds semantic search** (small, high-impact for rubric)
- 1–2 hours of work: on feedback=thumbs-up, upsert the question+SQL to RAG with `user_approved=True` metadata
- Directly addresses Conversational Quality (15%) and Innovation (10%) rubric criteria

### Pre-Demo Polish (Feb 27–Mar 7)

**P3: Statistician depth**
- Add 3–4 more statistical tools: chi-square test, Pearson correlation, trend decomposition, Z-score outlier detection
- Ensure statistician agent reliably runs on all question bank queries that warrant it

**P4: Model benchmarking (minimal viable)**
- Add `benchmarks` table, write a simple CLI runner that fires 30 tagged questions at Gemini 2.5 Flash vs 2.5 Pro
- Store results; add a read-only benchmark tab in admin panel
- This directly demonstrates technical sophistication to evaluators

**P5: CSV upload (scope-reduced)**
- Even a non-LLM version: upload CSV → infer DDL from pandas dtypes + column names → create table + seed dataset
- Skip the confidence-gated clarification for now; that's Phase 3a v2

### Post-Submission / If Advancing (Mar 8+)

**P6: Workflows** — saved query sequences, scheduled runs, email delivery

**P7: Discovery agent** — autonomous monitoring with threshold-based alerting

**P8: Tool routing** — category-based tool injection for 10+ tools per agent

---

## 6. Summary View

```
┌─────────────────────────────────────────────────────────────────┐
│                      FEATURE STATUS                             │
├─────────────────────────────────────────────────────────────────┤
│  Core pipeline (NL → SQL → chart → summary)        ✅ DONE      │
│  Clarification pre-check                           ✅ DONE      │
│  Prompts & DDL in DB                               ✅ DONE      │
│  Admin column/prompt editor                        ✅ DONE      │
│  User monitoring (admin conversation viewer)       ✅ DONE      │
│  Multi-org + feature toggles + branding            ✅ DONE      │
│  JWT auth + httpOnly cookies                       ✅ DONE      │
│  SSE streaming with chunk protocol                 ✅ DONE      │
│  ChromaDB RAG (4 collections, auto-save)           ✅ DONE      │
│  Gemini + Ollama + runtime switching               ✅ DONE      │
│  CI/CD (preview + Cloud Run + Firebase)            ✅ DONE      │
│  Test suite (16 files, 3,260 LOC)                  ✅ DONE      │
├─────────────────────────────────────────────────────────────────┤
│  Statistician agent                                ⚠️ PARTIAL   │
│  👍 reactions feed semantic search                 ❌ MISSING   │
├─────────────────────────────────────────────────────────────────┤
│  CSV upload with LLM DDL inference                 ❌ NOT DONE  │
│  Model benchmarking                                ❌ NOT DONE  │
│  50-tool expansion with smart routing              ❌ NOT DONE  │
│  Workflows + email notifications                   ❌ NOT DONE  │
│  Discovery agent                                   ❌ NOT DONE  │
└─────────────────────────────────────────────────────────────────┘
```

**Net assessment:** Phases 0–2b are complete and production-deployed. The system is a credible, feature-rich submission for the Techfest rubric as-is. The highest-leverage remaining work before Feb 28 is merging the current branch, running the question bank for regressions, and wiring thumbs-up into RAG retrieval (small change, visible impact on the Innovation criterion).
