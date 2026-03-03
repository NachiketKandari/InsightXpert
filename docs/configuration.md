# InsightXpert Configuration Reference

## Backend Environment Variables

The backend reads configuration from `backend/.env.local` via Pydantic Settings (`BaseSettings`). All values can also be set as regular shell environment variables; environment variables take precedence over `.env.local`.

The settings class is `insightxpert.config.Settings`.

---

### LLM Settings

**`LLM_PROVIDER`**
Which LLM backend to use.

| Value | Description |
|---|---|
| `gemini` | Google Gemini via AI Studio API key (default) |
| `ollama` | Local Ollama server |
| `vertex_ai` | Google Cloud Vertex AI Model Garden |

Default: `gemini`

---

**`GEMINI_API_KEY`**
Google AI Studio API key. Required when `LLM_PROVIDER=gemini`.

Obtain at: https://aistudio.google.com/app/apikey

Default: `""` (empty — a warning is logged at startup if the provider is Gemini and this is unset)

---

**`GEMINI_MODEL`**
Gemini model name to use.

Available models (also served by `GET /api/config`):
- `gemini-3-flash-preview`
- `gemini-3.1-pro-preview`
- `gemini-2.5-flash` ← **default**
- `gemini-2.5-pro`
- `gemini-2.5-flash-lite`
- `gemini-2.0-flash`
- `gemini-2.0-flash-lite`

Default: `gemini-2.5-flash`

---

**`OLLAMA_BASE_URL`**
URL of the Ollama HTTP server.

Default: `http://localhost:11434`

---

**`OLLAMA_MODEL`**
Default Ollama model name. Used when `LLM_PROVIDER=ollama`.

Default: `llama3.1`

Any model name accepted by Ollama is valid (e.g., `mistral`, `llama3.2:1b`, `codellama`). The model must be pulled before use.

---

**`GCP_PROJECT_ID`**
Google Cloud project ID for Vertex AI. When set, the `vertex_ai` provider becomes available in `GET /api/config`. Leave empty to disable Vertex AI.

Default: `""` (disabled)

---

**`VERTEX_AI_REGION`**
Google Cloud region for Vertex AI API calls.

Default: `global`

---

**`VERTEX_AI_MODEL`**
Model name for Vertex AI. Currently supports Model Garden models.

Default: `zai-org/glm-5-maas`

---

### Database Settings

**`DATABASE_URL`**
SQLAlchemy connection URL for the combined SQLite database. Both the transactions data and the auth/config data live in this file.

Default: `sqlite:///./insightxpert.db`

If set to an empty string, the default is used. The path is relative to the working directory where the server starts (`backend/` when using `python -m insightxpert.main`).

---

**`CHROMA_PERSIST_DIR`**
Directory for ChromaDB vector store persistence. Four collections are created here: `qa_pairs`, `ddl`, `docs`, `findings`.

Default: `./chroma_data`

---

### Security

**`SECRET_KEY`**
Secret used to sign and verify JWT session tokens. Must be at least 32 characters.

Default: `CHANGE-ME-in-production-use-a-random-secret-key-here`

A warning is logged at startup if the key contains `"CHANGE-ME"` or is shorter than 32 characters. Generate a strong key with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

**`ACCESS_TOKEN_EXPIRE_MINUTES`**
How long JWT session tokens remain valid, in minutes.

Default: `1440` (24 hours)

Must be greater than 0.

---

**`CORS_ORIGINS`**
Comma-separated list of allowed CORS origins. The backend will accept cross-origin requests from these URLs.

Default: `http://localhost:3000,https://insightxpert.vercel.app,https://insightxpert-ai.web.app`

Example for custom deployment:
```
CORS_ORIGINS=https://myapp.example.com,http://localhost:3000
```

---

### Admin Bootstrap

**`ADMIN_SEED_EMAIL`**
Email address for the bootstrap admin user created on first startup. If a user with this email already exists, seeding is skipped.

Default: `admin@insightxpert.ai`

---

**`ADMIN_SEED_PASSWORD`**
Password for the bootstrap admin user. Must be at least 8 characters. A warning is logged if this is set to common weak values (`changeme`, `admin123`, `""`).

Default: `admin123` (**must be changed for production**)

---

### Agent Settings

**`MAX_AGENT_ITERATIONS`**
Maximum number of LLM tool-call iterations for the analyst agent loop per request. Prevents runaway loops.

Default: `25`

Must be greater than 0.

---

**`MAX_QUANT_ANALYST_ITERATIONS`**
Maximum iterations for the quantitative analyst agent sub-loop (Python execution path).

Default: `15`

Must be greater than 0.

---

**`MAX_ORCHESTRATOR_TASKS`**
Maximum number of parallel sub-tasks the orchestrator planner can spawn per question in agentic mode.

Default: `10`

Must be greater than 0.

---

**`PYTHON_EXEC_TIMEOUT_SECONDS`**
Timeout in seconds for sandboxed Python code execution (used by the quantitative analyst).

Default: `10`

Must be greater than 0.

---

**`SQL_ROW_LIMIT`**
Maximum number of rows returned by any single SQL query. Applies to both the agent's internal queries and the `POST /api/sql/execute` endpoint.

Default: `10000`

Must be greater than 0.

---

**`SQL_TIMEOUT_SECONDS`**
Maximum execution time for any SQL query, in seconds.

Default: `30`

Must be greater than 0.

---

**`ENABLE_STATS_CONTEXT`**
When `true`, pre-computed dataset statistics are injected into the system prompt at the start of each chat request. Controlled per-user/org by the `stats_context_injection` feature toggle; this env var enables or disables the underlying computation.

Default: `true`

Set `ENABLE_STATS_CONTEXT=false` to disable the stats injection pipeline entirely.

---

### Startup and Runtime

**`RAG_BOOTSTRAP_TIMEOUT_SECONDS`**
Maximum time to wait for the background RAG training task to complete during startup. If training exceeds this limit the server starts anyway and continues training in the background.

Default: `120`

Must be greater than 0.

---

**`CONVERSATION_TTL_SECONDS`**
How long an in-memory conversation history entry is kept before being evicted. This is the in-process LLM context cache; persistent message storage in SQLite is not affected.

Default: `7200` (2 hours)

Must be greater than 0.

---

### Voice / Speech-to-Text

**`DEEPGRAM_API_KEY`**
API key for the Deepgram speech-to-text service. When set, the voice transcription feature is enabled via a WebSocket endpoint at `WS /api/transcribe`. The backend proxies browser audio to Deepgram's Nova-3 model and streams transcripts back in real time.

Obtain at: https://console.deepgram.com/

Default: `""` (empty — voice feature is disabled)

If a client connects to the `/api/transcribe` WebSocket and this key is not configured, the connection is closed with code `4002` and reason `"Speech-to-text is not configured"`.

---

### Cloudflare R2 Object Storage

R2 is used as optional backup storage for uploaded files (CSV datasets and PDF documents). It is not managed via the `Settings` class; instead, an `R2StorageService` instance is attached to `app.state.r2_storage` at startup when the required environment variables are present. If R2 is not configured, uploads are stored in the local SQLite database only and the R2 backup is silently skipped.

The following environment variables configure R2 (all four are required to enable R2):

**`R2_ACCESS_KEY_ID`**
Cloudflare R2 access key ID (S3-compatible).

**`R2_SECRET_ACCESS_KEY`**
Cloudflare R2 secret access key (S3-compatible).

**`R2_ENDPOINT_URL`**
Cloudflare R2 S3-compatible endpoint URL. Typically `https://<account-id>.r2.cloudflarestorage.com`.

**`R2_BUCKET`**
Name of the R2 bucket to store objects in.

All R2 operations (upload, delete, presigned URL generation) are synchronous and wrapped with `asyncio.to_thread()` in route handlers. Failures are logged but do not block the API response -- R2 is a best-effort backup layer.

---

### Logging

**`LOG_LEVEL`**
Logging verbosity for the `insightxpert.*` logger hierarchy.

Valid values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

Default: `INFO`

---

## Frontend Environment Variables

The frontend reads environment variables from `frontend/.env.local`. Variables prefixed with `NEXT_PUBLIC_` are embedded into the static build and visible in the browser.

**`NEXT_PUBLIC_API_URL`**
Base URL of the backend API. When empty, the frontend makes requests relative to its own origin (useful when running behind a reverse proxy).

Default: `""` (empty — relative URL)

Development `.env.local` typically sets:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

In the production CI build, this is set to the Cloud Run service URL discovered at deploy time.

**Why a direct URL in development:** Next.js rewrites buffer the full response before forwarding it, which breaks SSE streaming. Pointing directly at the backend bypasses the Next.js proxy so chunks stream incrementally.

---

## Admin Configuration

The admin configuration is stored in the database (`admin_config` table) as a JSON document. It is initially populated from the legacy `config/client-configs.json` file on first startup (idempotent migration), and thereafter managed exclusively via the admin UI or `PUT /api/admin/config`.

The full structure is the `ClientConfig` Pydantic model:

```json
{
  "admin_domains": ["insightxpert.ai"],
  "user_org_mappings": [
    {"email": "partner@acme.com", "org_id": "org-uuid"}
  ],
  "organizations": {
    "org-uuid": {
      "org_id": "org-uuid",
      "org_name": "ACME Corp",
      "features": {
        "sql_executor": true,
        "model_switching": false,
        "rag_training": false,
        "chart_rendering": true,
        "conversation_export": true,
        "agent_process_sidebar": true,
        "clarification_enabled": true,
        "stats_context_injection": true
      },
      "branding": {
        "display_name": "ACME Analytics",
        "logo_url": "https://acme.com/logo.png",
        "theme": {"--primary": "#FF6B00", "--secondary": "#003366"},
        "color_mode": "dark"
      }
    }
  },
  "defaults": {
    "features": {
      "sql_executor": true,
      "model_switching": true,
      "rag_training": true,
      "chart_rendering": true,
      "conversation_export": true,
      "agent_process_sidebar": true,
      "clarification_enabled": true,
      "stats_context_injection": false
    },
    "branding": {
      "display_name": null,
      "logo_url": null,
      "theme": null,
      "color_mode": null
    }
  }
}
```

### Field Descriptions

**`admin_domains`** — List of email domains whose users are automatically granted admin access, regardless of the `is_admin` DB flag. Example: `["insightxpert.ai"]` means `*@insightxpert.ai` are admins.

**`user_org_mappings`** — Email-to-org assignments. When a user logs in, their email is checked against this list to assign org membership. Each entry has `email` (exact match, case-insensitive) and `org_id`.

**`organizations`** — Map of `org_id` → `OrgConfig`. Each org has its own feature set and branding that overrides the defaults for mapped users.

**`defaults`** — Baseline `features` and `branding` applied to users who are not mapped to any org.

---

## Feature Toggles

Feature toggles are defined in `FeatureToggles` and control what UI capabilities are available to a user or org. They are resolved at request time via `GET /api/client-config`.

Admin users always receive all features enabled, regardless of org config.

| Toggle | Default | Description |
|---|---|---|
| `sql_executor` | `true` | Show the SQL Executor panel for running custom queries |
| `model_switching` | `true` | Allow users to switch LLM provider/model via the UI |
| `rag_training` | `true` | Allow users to add training examples to the RAG store |
| `chart_rendering` | `true` | Render Plotly charts for SQL results |
| `conversation_export` | `true` | Allow exporting conversations |
| `agent_process_sidebar` | `true` | Show the Agent Process sidebar with SQL traces and enrichment steps |
| `clarification_enabled` | `true` | Allow the LLM to ask clarifying questions before answering (also requires the backend feature toggle below) |
| `stats_context_injection` | `false` | Inject pre-computed dataset statistics into the system prompt for every chat request |

### Backend Feature Toggles

Two feature toggles are also enforced server-side during the agent loop (not just in the UI):

- **`stats_context_injection`** — If `false`, the stats context step is skipped even if the agent would otherwise include it.
- **`clarification_enabled`** — If `false`, the clarifier agent step is skipped and `skip_clarification` is implicitly `true`.

These are resolved per-request from the user's org config via `_resolve_user_features()` in `api/routes.py`.

---

## Pydantic Settings Class

`insightxpert.config.Settings` is a `pydantic_settings.BaseSettings` subclass. Full field list with defaults:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: LLMProvider = LLMProvider.GEMINI          # "gemini" | "ollama" | "vertex_ai"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434"

    # Vertex AI
    gcp_project_id: str = ""
    vertex_ai_region: str = "global"
    vertex_ai_model: str = "zai-org/glm-5-maas"

    # Database
    database_url: str = "sqlite:///./insightxpert.db"       # env: DATABASE_URL
    chroma_persist_dir: str = "./chroma_data"

    # Agent
    max_agent_iterations: int = 25                          # > 0
    max_quant_analyst_iterations: int = 15                  # > 0
    max_orchestrator_tasks: int = 10                        # > 0
    python_exec_timeout_seconds: int = 10                   # > 0
    sql_row_limit: int = 10000                              # > 0
    sql_timeout_seconds: int = 30                           # > 0

    # CORS
    cors_origins: str = "http://localhost:3000,https://insightxpert.vercel.app,https://insightxpert-ai.web.app"

    # Auth
    secret_key: str = "CHANGE-ME-..."                       # >= 32 chars for production
    access_token_expire_minutes: int = 1440                 # > 0
    admin_seed_email: str = "admin@insightxpert.ai"
    admin_seed_password: str = "admin123"                   # change for production

    # Startup / runtime
    rag_bootstrap_timeout_seconds: int = 120                # > 0
    conversation_ttl_seconds: int = 7200                    # > 0

    # Stats context
    enable_stats_context: bool = True

    # Voice / Speech-to-text (Deepgram)
    deepgram_api_key: str = ""

    # Logging
    log_level: str = "INFO"                                 # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

**Validators:**
- `database_url`: Empty string is treated as unset (falls back to default).
- `log_level`: Normalized to uppercase; invalid values raise `ValueError`.
- Model validator at startup logs warnings for insecure `secret_key`, weak `admin_seed_password`, missing `gemini_api_key` when provider is Gemini, and missing `gcp_project_id` when provider is Vertex AI.

---

## CI/CD: GitHub Actions Variables and Secrets

The production deploy workflow (`.github/workflows/deploy.yml`) uses Workload Identity Federation to authenticate to Google Cloud without storing a long-lived service account key.

### Secrets (required)

Stored in **Settings → Secrets → Actions** in the GitHub repository.

| Secret | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key for the Gemini LLM provider |
| `SECRET_KEY` | JWT signing secret — must be a random string of 32+ hex characters |
| `ADMIN_SEED_PASSWORD` | Password for the bootstrap admin account (replaces the insecure default) |

### Variables (optional overrides)

Stored in **Settings → Variables → Actions** in the GitHub repository. These have sensible defaults in the workflow but can be overridden per environment.

| Variable | Default in workflow | Description |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name passed to Cloud Run |
| `CORS_ORIGINS` | `https://insightxpert-ai.web.app,https://insightxpert.vercel.app` | Comma-separated allowed origins |

### Cloud Run Environment Variables (set by workflow)

The `gcloud run deploy` step passes these as `--set-env-vars`:

| Variable | Source |
|---|---|
| `LLM_PROVIDER` | Hardcoded to `gemini` |
| `GEMINI_API_KEY` | From secret `GEMINI_API_KEY` |
| `GEMINI_MODEL` | From variable `GEMINI_MODEL` (default: `gemini-2.5-flash`) |
| `DATABASE_URL` | `sqlite:///./insightxpert.db` |
| `LITESTREAM_REPLICA_URL` | `gcs://insightxpert-bucket/litestream/insightxpert.db` |
| `CHROMA_PERSIST_DIR` | `./chroma_data` |
| `CORS_ORIGINS` | From variable `CORS_ORIGINS` |
| `LOG_LEVEL` | `INFO` |
| `SECRET_KEY` | From secret `SECRET_KEY` |
| `ADMIN_SEED_PASSWORD` | From secret `ADMIN_SEED_PASSWORD` |

### Frontend Build Variable

The frontend build step sets `NEXT_PUBLIC_API_URL` to the Cloud Run service URL discovered dynamically via `gcloud run services describe`. This URL is baked into the static Next.js export and served from Firebase Hosting.

---

## Database Persistence in Production

The production Cloud Run instance uses **Litestream** for SQLite replication. Litestream runs as a sidecar and continuously replicates the local SQLite WAL to Google Cloud Storage (`gcs://insightxpert-bucket/litestream/insightxpert.db`). On container startup, Litestream restores the latest snapshot from GCS before the FastAPI server starts.

This means:
- All SQLite data (auth, conversations, config, automations, insights, stats) survives container restarts.
- The `transactions` table is populated from the CSV at startup if empty (as an additional safety net).
- ChromaDB vector data in `./chroma_data` is not replicated by Litestream; it is re-bootstrapped from the seeded training data on cold starts.

---

## Local Development Setup

Minimal `.env.local` for local development:

```dotenv
# backend/.env.local
GEMINI_API_KEY=your-api-key-here
SECRET_KEY=local-dev-secret-key-32-chars-min-here
ADMIN_SEED_PASSWORD=localdevpassword
LOG_LEVEL=DEBUG
```

Everything else uses defaults (SQLite at `./insightxpert.db`, ChromaDB at `./chroma_data`, Gemini 2.5 Flash, CORS allowing `localhost:3000`).

To also enable voice input during local development, add:

```dotenv
DEEPGRAM_API_KEY=your-deepgram-api-key-here
```

Minimal `frontend/.env.local`:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```
