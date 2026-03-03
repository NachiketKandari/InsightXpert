# InsightXpert REST API Reference

**Dev base URL:** `http://localhost:8000`
**Prod base URL:** `https://insightxpert-ai.web.app` (Firebase Hosting -> Cloud Run via rewrite)

## Authentication

All endpoints except `GET /api/health`, `POST /api/auth/login`, and `POST /api/auth/register` require authentication.

**Dual-path authentication:** The server supports two authentication methods:

| Method | Where used | How it works |
|---|---|---|
| `__session` HttpOnly cookie | Regular API calls (login, conversations, admin, etc.) via CDN proxy | Set automatically on login/register. First-party cookie because requests go through Firebase Hosting on the same origin. |
| `Authorization: Bearer <token>` header | SSE streaming (`POST /api/chat`) and WebSocket (`/api/transcribe`) via direct Cloud Run | Uses the `token` field returned in the login/register response body. Required because SSE goes directly to Cloud Run (to avoid buffering), making cookies third-party. |

The `get_current_user` dependency checks the `__session` cookie first, then falls back to the `Authorization: Bearer` header.

Cross-site requests (prod frontend to Cloud Run) use `SameSite=None; Secure`. Same-site requests (dev) use `SameSite=Lax`.

**401 Unauthorized** is returned when neither a valid cookie nor a valid Bearer token is present, or when the token is expired.

---

## Error Response Format

All error responses share a consistent JSON body regardless of which exception handler fires:

```json
{
  "error": "HTTP_ERROR",
  "detail": "Human-readable message",
  "status_code": 404
}
```

Common `error` values: `HTTP_ERROR`, `VALIDATION_ERROR`, `INTERNAL_ERROR`, `DATABASE_ERROR`, `QUERY_SYNTAX_ERROR`, `QUERY_TIMEOUT_ERROR`.

---

## Auth Endpoints

**Prefix:** `/api/auth`

### POST /api/auth/register

Register a new account. Automatically logs the user in by setting the session cookie and returning a JWT token in the response body.

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "mysecretpassword"
}
```

Password must be at least 8 characters.

**Response** `201 Created`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_admin": false,
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

The `token` field is a JWT that can be used as a Bearer token for SSE and WebSocket endpoints.

**Errors:**
- `409 Conflict` -- email already registered
- `422 Unprocessable Entity` -- password under 8 characters

---

### POST /api/auth/login

Authenticate an existing user. Sets the `__session` cookie on success and returns a JWT token in the response body.

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "mysecretpassword"
}
```

**Response** `200 OK`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_admin": false,
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Errors:**
- `401 Unauthorized` -- invalid email or password

---

### GET /api/auth/me

Return the currently authenticated user. The `token` field echoes back the token from the incoming request (cookie or Bearer header) rather than generating a new one.

**Response** `200 OK`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "is_admin": false,
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

---

### POST /api/auth/logout

Invalidate the session by deleting the `__session` cookie.

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

## Chat Endpoints

### POST /api/chat

Stream an AI response to a question via Server-Sent Events (SSE). The response is a stream of `ChatChunk` JSON objects, each on a `data:` SSE line, terminated by a `data: [DONE]` event.

**Auth:** Supports both cookie and `Authorization: Bearer <token>` header. In production, this endpoint is called directly against Cloud Run (bypassing CDN proxy) to avoid SSE buffering, so Bearer token auth is the primary method.

**Request body:**
```json
{
  "message": "What are the top 5 merchant categories by transaction volume?",
  "conversation_id": null,
  "agent_mode": "agentic",
  "skip_clarification": false
}
```

| Field | Type | Description |
|---|---|---|
| `message` | `string` | The user's question |
| `conversation_id` | `string \| null` | Continue an existing conversation, or `null` to start a new one |
| `agent_mode` | `"basic" \| "agentic" \| "deep"` | Analysis depth. Default: `"agentic"` |
| `skip_clarification` | `bool` | If `true`, bypass the clarification step even when enabled. Default: `false` |

Legacy mode aliases: `"auto"` -> `"agentic"`, `"statistician"` -> `"agentic"`, `"advanced"` -> `"agentic"`, `"analyst"` -> `"basic"`.

**Response:** `text/event-stream`

Each event is a JSON-serialized `ChatChunk` object. See the [ChatChunk Schema](#chatchunk-schema) section for all type definitions.

Example SSE stream:
```
data: {"type":"status","content":"Analysing question...","data":{"agent":"orchestrator","phase":"start"},"conversation_id":"abc123","timestamp":1700000000.0}

data: {"type":"sql","sql":"SELECT merchant_category, SUM(amount) AS total FROM transactions GROUP BY merchant_category ORDER BY total DESC LIMIT 5","conversation_id":"abc123","timestamp":1700000001.0}

data: {"type":"answer","content":"The top 5 merchant categories by total transaction value are...","conversation_id":"abc123","timestamp":1700000002.0}

data: {"type":"metrics","data":{"input_tokens":1234,"output_tokens":456,"generation_time_ms":2341},"conversation_id":"abc123","timestamp":1700000002.0}

data: [DONE]
```

The `conversation_id` in each chunk is the ID to use for subsequent turns. If you passed `null` for `conversation_id`, use the ID from the first chunk for follow-up messages.

---

### POST /api/chat/poll

Non-streaming version of `/api/chat`. Runs the full pipeline to completion and returns all chunks at once.

**Request body:** Same as `POST /api/chat`.

**Response** `200 OK`:
```json
{
  "chunks": [
    {"type": "status", "content": "Analysing question...", "conversation_id": "abc123", "timestamp": 1700000000.0},
    {"type": "sql", "sql": "SELECT ...", "conversation_id": "abc123", "timestamp": 1700000001.0},
    {"type": "answer", "content": "The top 5...", "conversation_id": "abc123", "timestamp": 1700000002.0}
  ]
}
```

---

### POST /api/chat/answer

Run the full pipeline and return only the final answer, conversation ID, and any SQL queries that were executed. Useful for programmatic integrations that do not need the intermediate trace.

**Request body:** Same as `POST /api/chat`.

**Response** `200 OK`:
```json
{
  "answer": "The top 5 merchant categories by total transaction value are...",
  "conversation_id": "abc123",
  "sql": [
    "SELECT merchant_category, SUM(amount) AS total FROM transactions GROUP BY merchant_category ORDER BY total DESC LIMIT 5"
  ]
}
```

---

## Conversation Endpoints

### GET /api/conversations

List all conversations for the current user, ordered by most recently updated.

`Cache-Control: private, max-age=5`

**Response** `200 OK`:
```json
[
  {
    "id": "abc123",
    "title": "Top merchant categories by volume",
    "is_starred": false,
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:32:00",
    "last_message": "The top 5 merchant categories..."
  }
]
```

---

### GET /api/conversations/search?q={keyword}

Full-text search across conversation titles and message content. Returns nothing if `q` is shorter than 2 characters.

**Query parameters:**
- `q` -- Search keyword (minimum 2 characters)

**Response** `200 OK`:
```json
[
  {
    "id": "abc123",
    "title": "Top merchant categories by volume",
    "updated_at": "2024-01-15T10:32:00",
    "title_match": true,
    "matching_messages": [
      {
        "role": "user",
        "snippet": "What are the top merchant categories...",
        "created_at": "2024-01-15T10:30:00"
      }
    ]
  }
]
```

---

### GET /api/conversations/{id}

Get a conversation with all its messages. `tool_result` rows in historical chunks are truncated to 50 rows to reduce payload size; the original row count is preserved in `original_row_count`.

**Response** `200 OK`:
```json
{
  "id": "abc123",
  "title": "Top merchant categories by volume",
  "is_starred": false,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:32:00",
  "messages": [
    {
      "id": "msg001",
      "role": "user",
      "content": "What are the top 5 merchant categories?",
      "chunks": null,
      "feedback": null,
      "feedback_comment": null,
      "input_tokens": null,
      "output_tokens": null,
      "generation_time_ms": null,
      "created_at": "2024-01-15T10:30:00"
    },
    {
      "id": "msg002",
      "role": "assistant",
      "content": "The top 5 merchant categories are...",
      "chunks": [
        {"type": "sql", "sql": "SELECT ...", "conversation_id": "abc123", "timestamp": 1700000001.0},
        {"type": "answer", "content": "The top 5...", "conversation_id": "abc123", "timestamp": 1700000002.0}
      ],
      "feedback": null,
      "feedback_comment": null,
      "input_tokens": 1234,
      "output_tokens": 456,
      "generation_time_ms": 2341,
      "created_at": "2024-01-15T10:30:05"
    }
  ]
}
```

The `feedback` field is a boolean (`true` = thumbs up, `false` = thumbs down, `null` = no feedback).

**Errors:**
- `404 Not Found` -- conversation not found or belongs to another user

---

### PATCH /api/conversations/{id}

Rename a conversation.

**Request body:**
```json
{"title": "New conversation title"}
```

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:**
- `404 Not Found`

---

### PATCH /api/conversations/{id}/star

Star or unstar a conversation.

**Request body:**
```json
{"starred": true}
```

**Response** `200 OK`:
```json
{"status": "ok", "starred": true}
```

---

### DELETE /api/conversations/{id}

Delete a conversation and all its messages.

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:**
- `404 Not Found`

---

## SQL Endpoints

### POST /api/sql/execute

Execute a read-only SQL query directly against the transactions database.

Write operations are blocked via regex (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `REPLACE`, `MERGE`, `GRANT`, `REVOKE`, `ATTACH`, `DETACH`, and `PRAGMA x =`) and SQLite's `PRAGMA query_only = ON`.

Results are capped at the configured `SQL_ROW_LIMIT` (default: 10,000 rows).

**Request body:**
```json
{"sql": "SELECT transaction_type, COUNT(*) AS cnt FROM transactions GROUP BY transaction_type"}
```

**Response** `200 OK`:
```json
{
  "columns": ["transaction_type", "cnt"],
  "rows": [
    {"transaction_type": "P2P", "cnt": 125000},
    {"transaction_type": "P2M", "cnt": 125000}
  ],
  "row_count": 2,
  "execution_time_ms": 12.34
}
```

**Errors:**
- `400 Bad Request` -- empty SQL
- `403 Forbidden` -- SQL contains a blocked write/admin keyword
- `400 QUERY_SYNTAX_ERROR` -- SQL syntax error
- `408 QUERY_TIMEOUT_ERROR` -- query exceeded `SQL_TIMEOUT_SECONDS`
- `503 DATABASE_CONNECTION_ERROR` -- cannot reach database
- `500 DATABASE_ERROR` -- other execution error

---

### GET /api/sql/export-csv?table={table_name}

Stream an entire table as a CSV file download. The table name is validated against the list of known tables to prevent SQL injection.

**Query parameters:**
- `table` -- Table name (default: `transactions`). Must be a known table.

**Response** `200 OK` -- `Content-Type: text/csv`, streaming

The `Content-Disposition` header is `attachment; filename="insightxpert-{table}.csv"`.

**Errors:**
- `400 Bad Request` -- unknown table name

---

## Schema & Training

### GET /api/schema

Return the database DDL and list of tables.

`Cache-Control: private, max-age=3600`

**Response** `200 OK`:
```json
{
  "ddl": "CREATE TABLE transactions (\n  transaction_id TEXT PRIMARY KEY,\n  ...\n)",
  "tables": ["transactions"]
}
```

---

### POST /api/train

Add an item to the RAG vector store. Used to improve SQL generation quality over time.

**Request body:**
```json
{
  "type": "qa_pair",
  "content": "What is the total transaction amount by city?",
  "metadata": {
    "sql": "SELECT city, SUM(amount) FROM transactions GROUP BY city",
    "sql_valid": true
  }
}
```

| `type` | `content` | `metadata` |
|---|---|---|
| `qa_pair` | Natural-language question | `{"sql": "...", "sql_valid": true}` |
| `ddl` | DDL statement | `{"table_name": "transactions"}` |
| `documentation` | Free-text business context | `{}` or any key-value pairs |

**Response** `200 OK`:
```json
{"status": "ok", "id": "chroma-doc-id"}
```

**Errors:**
- `200 OK` with `{"status": "error", "id": ""}` -- unknown `type` value

---

### DELETE /api/rag

Delete all RAG embeddings from all four ChromaDB collections: `qa_pairs`, `ddl`, `docs`, and `findings`.

**Response** `200 OK`:
```json
{
  "status": "ok",
  "deleted": {
    "qa_pairs": 42,
    "ddl": 1,
    "docs": 5,
    "findings": 0
  }
}
```

---

## Config & Model Switching

### GET /api/config

Get the current LLM configuration and the list of available providers and models. Ollama is only advertised if the Ollama server is reachable and has at least one model pulled.

`Cache-Control: private, max-age=60`

**Response** `200 OK`:
```json
{
  "current_provider": "gemini",
  "current_model": "gemini-2.5-flash",
  "providers": [
    {
      "provider": "gemini",
      "models": [
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite"
      ]
    },
    {
      "provider": "ollama",
      "models": ["llama3.2", "mistral"]
    }
  ]
}
```

`vertex_ai` appears in `providers` only when `GCP_PROJECT_ID` is configured.

---

### POST /api/config/switch

Switch the active LLM provider and model at runtime. The change takes effect immediately for all subsequent chat requests. If switching to Ollama, the model is validated against the Ollama server before the switch occurs. If `create_llm` fails, settings are rolled back to the previous values.

**Request body:**
```json
{"provider": "gemini", "model": "gemini-2.5-pro"}
```

Valid `provider` values: `"gemini"`, `"ollama"`, `"vertex_ai"`.

**Response** `200 OK`:
```json
{"provider": "gemini", "model": "gemini-2.5-pro"}
```

**Errors:**
- `503 Service Unavailable` -- Ollama unreachable or model not found
- `400 Bad Request` -- provider validation failed

---

## Ollama Model Management

### POST /api/ollama/pull

Download an Ollama model. Streams download progress via SSE.

**Request body:**
```json
{"model": "llama3.2"}
```

**Response:** `text/event-stream`

Progress events:
```
data: {"status": "pulling manifest"}

data: {"status": "downloading", "completed": 524288000, "total": 2048000000, "percent": 25.6, "digest": "sha256:abc..."}

data: {"status": "success", "model": "llama3.2"}

data: [DONE]
```

Error event:
```
data: {"status": "error", "detail": "model not found"}

data: [DONE]
```

---

### GET /api/ollama/models

List all locally available Ollama models.

**Response** `200 OK`:
```json
{
  "models": [
    {
      "model": "llama3.2",
      "size_mb": 2048.1,
      "parameter_size": "3B",
      "quantization": "Q4_0",
      "family": "llama"
    }
  ]
}
```

**Errors:**
- `503 Service Unavailable` -- Ollama is not reachable

---

### DELETE /api/ollama/models/{model_name}

Delete a locally downloaded Ollama model. The `model_name` path segment supports slashes (e.g., `llama3.2:latest`).

**Response** `200 OK`:
```json
{"status": "ok", "model": "llama3.2"}
```

**Errors:**
- `400 Bad Request` -- model not found or delete failed

---

## Feedback

### POST /api/feedback

Submit or update thumbs-up / thumbs-down feedback on an assistant message.

**Request body:**
```json
{
  "message_id": "msg002",
  "feedback": true,
  "comment": "Great answer, very accurate."
}
```

| Field | Type | Description |
|---|---|---|
| `message_id` | `string` | The assistant message ID |
| `feedback` | `true \| false \| null` | `true` = thumbs up, `false` = thumbs down, `null` = clear feedback |
| `comment` | `string \| null` | Optional free-text comment |

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:**
- `404 Not Found` -- message not found or belongs to another user

---

## Stats

### GET /api/stats

Return pre-computed dataset statistics, grouped by stat group and dimension. Statistics are computed at startup and cached; this endpoint reads from the `dataset_stats` SQLite table.

**Response** `200 OK`:
```json
{
  "groups": {
    "by_type": {
      "P2P": {
        "count": 125000,
        "avg_amount": 2341.5,
        "total_amount": 292687500.0
      },
      "P2M": {
        "count": 125000,
        "avg_amount": 1876.3,
        "total_amount": 234537500.0
      }
    },
    "by_city": {
      "Mumbai": {"count": 45000, "avg_amount": 2100.0}
    }
  },
  "computed_at": "2024-01-15 09:00:00"
}
```

---

## Health

### GET /api/health

Health check -- no authentication required. Also available at `GET /health`.

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

## Voice Endpoints

### WebSocket /api/transcribe

Real-time speech-to-text via Deepgram Nova-3. The client sends audio frames over a WebSocket; the server proxies them to the Deepgram streaming API and relays transcription results back to the client.

**Auth:** The WebSocket is authenticated via one of:
1. `__session` cookie (sent automatically by the browser)
2. `token` query parameter (e.g., `ws://localhost:8000/api/transcribe?token=eyJ...`)

If neither is present or valid, the WebSocket is closed with code `4001` and reason `"Not authenticated"`.

**Prerequisites:** The `DEEPGRAM_API_KEY` environment variable must be configured. If missing, the WebSocket is closed with code `4002` and reason `"Speech-to-text is not configured"`.

**Protocol:**

1. Client opens WebSocket connection to `/api/transcribe`
2. Server authenticates and connects to Deepgram Nova-3 (`wss://api.deepgram.com/v1/listen`)
3. Client sends binary audio frames (WebM/Opus container, encoding auto-detected by Deepgram)
4. Server relays JSON transcription results back as text messages

**Deepgram parameters:**
- `model`: `nova-3`
- `language`: `en`
- `punctuate`: `true`
- `interim_results`: `true`
- `utterance_end_ms`: `1000`
- `smart_format`: `true`

**Transcription result (text message from server):**
```json
{
  "type": "Results",
  "channel": {
    "alternatives": [
      {
        "transcript": "What are the top merchant categories?",
        "confidence": 0.98
      }
    ]
  },
  "is_final": true
}
```

**Error (text message from server):**
```json
{"error": "Voice connection failed"}
```

The WebSocket is closed with code `1011` if the Deepgram connection fails after the initial handshake.

---

## Document Endpoints

**Prefix:** `/api/documents`

Manage PDF documents uploaded for RAG-enhanced analysis. Documents are processed (text extraction), stored in the database, and optionally backed up to R2 cloud storage.

### POST /api/documents/upload

Upload a PDF document. The file is validated, text is extracted, and a database record is created. If R2 storage is configured, the original file is uploaded in the background.

**Auth:** Any authenticated user.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `file` | Yes | PDF file (max 20 MB) |
| `name` | `string` | Yes | Display name for the document |
| `description` | `string` | No | Optional description |
| `dataset_id` | `string` | No | Associate with a dataset |

**Response** `200 OK`:
```json
{
  "id": "doc-abc123",
  "name": "Q4 Financial Report",
  "description": "Quarterly financial analysis",
  "file_name": "q4-report.pdf",
  "file_type": "application/pdf",
  "file_size_bytes": 1048576,
  "page_count": 12,
  "dataset_id": "ds-abc",
  "created_by": "user-id",
  "created_at": "2024-01-15T10:30:00"
}
```

**Errors:**
- `400 Bad Request` -- not a PDF file, empty file, or processing failure
- `413 Payload Too Large` -- file exceeds 20 MB
- `503 Service Unavailable` -- document service not available

---

### GET /api/documents

List all documents visible to the current user. Super admins see all documents; regular users see documents they created.

**Auth:** Any authenticated user.

**Response** `200 OK` -- array of document objects.

---

### DELETE /api/documents/{doc_id}

Delete a document record and its R2 storage (if applicable). Admins can delete any document; regular users can only delete their own.

**Auth:** Any authenticated user (ownership or admin required).

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:**
- `403 Forbidden` -- not the owner and not an admin
- `404 Not Found` -- document not found

---

## Dataset Endpoints

**Prefix:** `/api/datasets`

### GET /api/datasets

List all datasets (super admin only).

**Auth:** Super admin required.

**Response** `200 OK` -- array of dataset objects with `id`, `name`, `description`, `ddl`, `documentation`, `is_active`, `table_name`, `organization_id`, `created_by`, `created_at`, `updated_at`.

---

### GET /api/datasets/public

List datasets visible to the current user. System datasets (no `created_by`) are visible to everyone. User-uploaded datasets are visible only to the uploader and super admins.

**Auth:** Any authenticated user.

**Response** `200 OK`:
```json
[
  {
    "id": "ds-abc",
    "name": "transactions",
    "description": "250,000 Indian UPI digital payment transactions from 2024",
    "is_active": true,
    "table_name": "transactions",
    "organization_id": null,
    "created_by": null
  }
]
```

---

### GET /api/datasets/public/{dataset_id}/columns

Return column metadata for a dataset. Enforces user-scope: user-uploaded datasets can only be accessed by the owner or a super admin.

**Auth:** Any authenticated user (ownership enforced for user-uploaded datasets).

**Response** `200 OK` -- array of column objects with `column_name`, `column_type`, `description`, `domain_values`, `domain_rules`, `ordinal_position`.

**Errors:**
- `403 Forbidden` -- dataset belongs to another user and caller is not a super admin
- `404 Not Found` -- dataset not found

---

### POST /api/datasets/upload

Upload a CSV file to create a new dataset. The dataset is created inactive and owned by the uploading user. If R2 storage is configured, the CSV is backed up in the background.

**Auth:** Any authenticated user.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `file` | Yes | CSV file (max 50 MB) |
| `name` | `string` | Yes | Display name for the dataset |
| `description` | `string` | No | Optional description |

**Response** `200 OK`:
```json
{
  "id": "ds-new123",
  "name": "My Custom Dataset",
  "description": "Uploaded transaction subset",
  "table_name": "ds_new123",
  "is_active": false,
  "created_by": "user-id",
  "created_at": "2024-01-15T10:30:00"
}
```

**Errors:**
- `400 Bad Request` -- not a CSV file, empty file, or parsing error
- `413 Payload Too Large` -- file exceeds 50 MB
- `503 Service Unavailable` -- dataset service not available

---

### POST /api/datasets/{dataset_id}/confirm

Confirm a dataset after upload by providing column descriptions and profiler output. Compiles rich documentation from the profiler data and user-provided descriptions. Only the dataset owner or an admin can confirm.

**Auth:** Dataset owner or admin.

**Request body:**
```json
{
  "column_descriptions": {
    "amount": "Transaction amount in INR",
    "city": "City where the transaction occurred"
  },
  "profile": {
    "row_count": 50000,
    "column_count": 12,
    "columns": [
      {
        "name": "amount",
        "original_name": "Amount",
        "inferred_type": "REAL",
        "distinct_count": 48234,
        "null_count": 0,
        "null_percent": 0.0,
        "is_unique": false,
        "cardinality": "high",
        "unique_values": null,
        "min": 10.0,
        "max": 99999.0,
        "mean": 2341.5
      }
    ]
  }
}
```

**Response** `200 OK` -- the updated dataset object.

**Errors:**
- `403 Forbidden` -- not the owner and not an admin
- `404 Not Found` -- dataset not found

---

### DELETE /api/datasets/{dataset_id}

Delete a dataset and its underlying data table. Owners can delete their own datasets; admins can delete any dataset. If R2 storage is configured, the backup file is cleaned up in the background.

**Auth:** Dataset owner or admin.

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:**
- `403 Forbidden` -- not the owner and not an admin
- `404 Not Found` -- dataset not found

---

### POST /api/datasets/{dataset_id}/activate

Set a dataset as the active dataset. System datasets can be activated by any authenticated user. User-uploaded datasets can only be activated by the owner or a super admin.

**Auth:** Any authenticated user (ownership enforced for user-uploaded datasets).

**Response** `200 OK`:
```json
{"status": "ok", "active_dataset_id": "ds-abc"}
```

**Errors:**
- `403 Forbidden` -- user-uploaded dataset and caller is not owner or super admin
- `404 Not Found` -- dataset not found

---

### GET /api/datasets/{dataset_id}

Get full dataset detail including columns and example queries (super admin only).

**Auth:** Super admin required.

**Errors:** `404 Not Found`

---

### PUT /api/datasets/{dataset_id}

Update dataset metadata (super admin only). All fields are optional.

**Auth:** Super admin required.

**Request body:**
```json
{
  "name": "transactions",
  "description": "Updated description",
  "ddl": "CREATE TABLE transactions (...)",
  "documentation": "Business context...",
  "organization_id": null
}
```

---

### POST /api/datasets/{dataset_id}/columns

Add a column definition (super admin only).

**Auth:** Super admin required.

**Request body:**
```json
{
  "column_name": "merchant_category",
  "column_type": "TEXT",
  "description": "Category of the merchant",
  "domain_values": "Food, Travel, Entertainment, Retail",
  "domain_rules": null,
  "ordinal_position": 5
}
```

---

### PUT /api/datasets/{dataset_id}/columns/{col_id}

Update a column definition (super admin only).

**Auth:** Super admin required.

---

### POST /api/datasets/{dataset_id}/queries

Add an example question-SQL pair (super admin only).

**Auth:** Super admin required.

**Request body:**
```json
{
  "question": "What is the total transaction amount by city?",
  "sql": "SELECT city, SUM(amount) FROM transactions GROUP BY city ORDER BY SUM(amount) DESC",
  "category": "aggregation"
}
```

---

### DELETE /api/datasets/{dataset_id}/queries/{query_id}

Delete an example query (super admin only).

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

### POST /api/datasets/{dataset_id}/retrain

Re-run RAG training for a specific dataset, reloading its DDL, documentation, and example queries into ChromaDB (super admin only).

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{"status": "ok", "items_trained": 47}
```

---

## Admin Endpoints

All admin endpoints require `is_admin=true` or an email from a configured admin domain. Org admins are scoped to their own organization's data. Super admins (no `org_id`) have unrestricted access.

**Auth:** `403 Forbidden` when the authenticated user is not an admin.

---

### GET /api/admin/users

List all users with conversation and message counts. Org admins see only users in their org.

**Response** `200 OK`:
```json
{
  "users": [
    {
      "id": "550e8400...",
      "email": "user@example.com",
      "is_admin": false,
      "org_id": "org-abc",
      "conversation_count": 12,
      "message_count": 48,
      "last_active": "2024-01-15T10:30:00"
    }
  ]
}
```

---

### GET /api/admin/users/{user_id}/conversations

List all conversations for a specific user (org-scoped).

**Response** `200 OK`:
```json
{
  "conversations": [
    {
      "id": "abc123",
      "title": "Top merchant categories",
      "is_starred": false,
      "org_id": "org-abc",
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:32:00"
    }
  ]
}
```

---

### GET /api/admin/conversations/{id}

Get full conversation detail including all messages and chunk data. Org admins can only access conversations belonging to their org.

**Response** `200 OK` -- same shape as `GET /api/conversations/{id}` with the addition of `org_id` on the conversation.

---

### DELETE /api/admin/conversations/{id}

Delete any conversation (org-scoped).

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

### DELETE /api/admin/conversations/user/{user_id}

Delete all conversations for a specific user (org-scoped).

**Response** `200 OK`:
```json
{"status": "ok", "deleted_count": 12}
```

---

### DELETE /api/admin/conversations

Delete all conversations. Super admins delete all platform conversations; org admins delete only their org's conversations.

**Response** `200 OK`:
```json
{"status": "ok", "deleted_count": 247}
```

---

### GET /api/admin/config

Get the full `ClientConfig` including `defaults`, `organizations`, `user_org_mappings`, and `admin_domains`.

**Response** `200 OK`:
```json
{
  "admin_domains": ["insightxpert.ai"],
  "user_org_mappings": [
    {"email": "partner@acme.com", "org_id": "org-acme"}
  ],
  "organizations": {
    "org-acme": {
      "org_id": "org-acme",
      "org_name": "ACME Corp",
      "features": {
        "sql_executor": true,
        "model_switching": false,
        "rag_training": false,
        "rag_retrieval": true,
        "chart_rendering": true,
        "conversation_export": true,
        "agent_process_sidebar": false,
        "clarification_enabled": true,
        "stats_context_injection": true
      },
      "branding": {
        "display_name": "ACME Analytics",
        "logo_url": "https://acme.com/logo.png",
        "theme": {"--primary": "#FF6B00"},
        "color_mode": "dark"
      }
    }
  },
  "defaults": {
    "features": { ... },
    "branding": { ... }
  }
}
```

---

### PUT /api/admin/config

Update global defaults: `admin_domains`, `user_org_mappings`, and/or `defaults`. All fields are optional; only provided fields are updated.

**Auth:** Super admin required.

**Request body:**
```json
{
  "admin_domains": ["insightxpert.ai", "mycompany.com"],
  "defaults": {
    "features": {
      "stats_context_injection": true,
      "clarification_enabled": false
    },
    "branding": {}
  }
}
```

**Response** `200 OK` -- the full updated `ClientConfig`.

---

### GET /api/admin/organizations

List all organizations (IDs and names).

**Response** `200 OK`:
```json
{
  "organizations": [
    {"org_id": "org-acme", "org_name": "ACME Corp"}
  ]
}
```

---

### POST /api/admin/organizations

Create a new organization.

**Auth:** Super admin required.

**Request body:**
```json
{"org_name": "New Org"}
```

**Response** `200 OK` -- the created `OrgConfig` object.

---

### GET /api/admin/config/{org_id}

Get configuration for a specific organization.

**Response** `200 OK` -- `OrgConfig` object.

**Errors:** `404 Not Found`

---

### PUT /api/admin/config/{org_id}

Create or update an organization's full configuration (features and branding).

**Request body:** Full `OrgConfig` object.
```json
{
  "org_id": "org-acme",
  "org_name": "ACME Corp",
  "features": {
    "sql_executor": true,
    "model_switching": false,
    "rag_training": false,
    "rag_retrieval": true,
    "chart_rendering": true,
    "conversation_export": true,
    "agent_process_sidebar": true,
    "clarification_enabled": true,
    "stats_context_injection": true
  },
  "branding": {
    "display_name": "ACME Analytics",
    "logo_url": "https://acme.com/logo.png",
    "theme": null,
    "color_mode": null
  }
}
```

**Response** `200 OK` -- the updated `OrgConfig`.

---

### DELETE /api/admin/config/{org_id}

Delete an organization.

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:** `404 Not Found`

---

### DELETE /api/admin/rag/qa-pairs

Flush all QA pairs from ChromaDB, leaving DDL, documentation, and findings collections intact. Useful when retraining from scratch.

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{"status": "ok", "deleted_count": 42}
```

---

### GET /api/admin/prompts

List all prompt templates stored in the database.

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{
  "prompts": [
    {
      "id": "550e8400...",
      "name": "analyst_system",
      "content": "You are an expert SQL analyst...",
      "description": "System prompt for the SQL analyst agent",
      "is_active": true,
      "created_at": "2024-01-15T10:00:00",
      "updated_at": "2024-01-15T10:00:00"
    }
  ]
}
```

---

### GET /api/admin/prompts/{name}

Get a specific prompt template by name. Name must match `^[a-z][a-z0-9_]{0,99}$`.

**Auth:** Super admin required.

**Response** `200 OK` -- single prompt template object.

**Errors:** `404 Not Found`

---

### PUT /api/admin/prompts/{name}

Create or update a prompt template (upsert).

**Auth:** Super admin required.

**Request body:**
```json
{
  "content": "You are an expert SQL analyst for Indian payment data...",
  "description": "System prompt for the SQL analyst agent",
  "is_active": true
}
```

**Response** `200 OK`:
```json
{"status": "ok", "name": "analyst_system"}
```

---

### DELETE /api/admin/prompts/{name}

Delete a prompt template. The agent falls back to the bundled `.j2` file template.

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{"status": "ok", "name": "analyst_system"}
```

---

### POST /api/admin/prompts/{name}/reset

Reset a prompt template to the content of its bundled `.j2` file.

**Auth:** Super admin required.

**Response** `200 OK`:
```json
{"status": "ok", "name": "analyst_system"}
```

**Errors:** `404 Not Found` -- no `.j2` file exists for the given name

---

## Client Config (Non-Admin)

### GET /api/client-config

Resolve the effective configuration for the current user. Returns the merged feature toggles and branding based on the user's organization membership.

- Admin users receive all features enabled.
- Org-mapped users receive their organization's feature set.
- Unaffiliated users receive the global defaults.

**Response** `200 OK`:
```json
{
  "config": {
    "org_id": "org-acme",
    "org_name": "ACME Corp",
    "features": {
      "sql_executor": true,
      "model_switching": false,
      "rag_training": false,
      "rag_retrieval": true,
      "chart_rendering": true,
      "conversation_export": true,
      "agent_process_sidebar": true,
      "clarification_enabled": true,
      "stats_context_injection": true
    },
    "branding": {
      "display_name": "ACME Analytics",
      "logo_url": "https://acme.com/logo.png",
      "theme": null,
      "color_mode": null
    }
  },
  "is_admin": false,
  "org_id": "org-acme"
}
```

---

## Automation Endpoints

**Prefix:** `/api/automations` (admin only)

Automations run SQL queries on a cron schedule and fire alert notifications when trigger conditions are met.

### POST /api/automations/generate-sql

Generate a SQL query from a natural-language prompt using the analyst agent (admin only).

**Request body:**
```json
{"prompt": "Find transactions where the average amount per merchant exceeds 5000"}
```

**Response** `200 OK`:
```json
{
  "sql": "SELECT merchant_id, AVG(amount) AS avg_amount FROM transactions GROUP BY merchant_id HAVING AVG(amount) > 5000",
  "explanation": "This query groups transactions by merchant and filters..."
}
```

**Errors:**
- `422 Unprocessable Entity` -- no SQL could be generated from the prompt

---

### POST /api/automations/compile-trigger

Compile a natural-language trigger description into a structured condition (admin only).

**Request body:**
```json
{
  "nl_text": "Alert when total fraud transactions exceed 1000",
  "available_columns": ["transaction_type", "amount", "is_fraud"]
}
```

**Response** `200 OK` -- `TriggerCondition` object.

---

### POST /api/automations

Create an automation (admin only).

**Request body:**
```json
{
  "name": "Daily Fraud Alert",
  "description": "Alert when fraud count spikes",
  "nl_query": "Count fraud transactions today",
  "sql_queries": [
    "SELECT COUNT(*) AS fraud_count FROM transactions WHERE is_fraud = 1 AND date(timestamp) = date('now')"
  ],
  "schedule_preset": "daily",
  "trigger_conditions": [
    {
      "type": "threshold",
      "column": "fraud_count",
      "operator": "gt",
      "value": 100
    }
  ],
  "source_conversation_id": null,
  "source_message_id": null,
  "workflow_graph": null
}
```

`schedule_preset` values: `"hourly"` (`0 * * * *`), `"daily"` (`0 9 * * *`), `"weekly"` (`0 9 * * 1`), `"monthly"` (`0 9 1 * *`). Alternatively, provide `cron_expression` (5-field cron string). One is required.

`sql_queries` is an ordered chain of SELECT-only queries. `sql_query` (single string) is also accepted for backward compatibility.

`workflow_graph` is an optional `{ blocks, edges }` object for the visual workflow builder UI.

**Trigger condition types:**

| `type` | Description | Key fields |
|---|---|---|
| `threshold` | Fire when a column value crosses a threshold | `column`, `operator` (`gt`, `gte`, `lt`, `lte`, `eq`, `ne`), `value` |
| `change_detection` | Fire when a value changes by a percentage | `column`, `change_percent` |
| `row_count` | Fire based on the number of rows returned | `operator`, `value` |
| `column_expression` | Fire based on a column expression across rows | `column`, `operator`, `value`, `scope` (`any_row`, `all_rows`) |
| `slope` | Fire based on the trend slope across recent runs | `column`, `operator`, `value`, `slope_window` (default: 5) |

**Response** `200 OK` -- automation object.

---

### GET /api/automations

List automations. Org admins see automations in their org; super admins see all.

**Auth:** Admin required.

**Response** `200 OK` -- array of automation objects.

---

### GET /api/automations/{id}

Get automation detail including the 10 most recent runs (admin only).

**Response** `200 OK`:
```json
{
  "id": "auto-abc",
  "name": "Daily Fraud Alert",
  "description": "Alert when fraud count spikes",
  "nl_query": "Count fraud transactions today",
  "sql_query": "SELECT COUNT(*) AS fraud_count FROM transactions WHERE is_fraud = 1",
  "sql_queries": ["SELECT COUNT(*) AS fraud_count FROM transactions WHERE is_fraud = 1"],
  "cron_expression": "0 9 * * *",
  "trigger_conditions": [
    {"type": "threshold", "column": "fraud_count", "operator": "gt", "value": 100}
  ],
  "is_active": true,
  "last_run_at": "2024-01-15T09:00:00",
  "next_run_at": "2024-01-16T09:00:00",
  "created_by": "user-id",
  "source_conversation_id": null,
  "source_message_id": null,
  "workflow_graph": null,
  "created_at": "2024-01-10T12:00:00",
  "updated_at": "2024-01-15T09:00:01",
  "recent_runs": [...]
}
```

---

### PUT /api/automations/{id}

Update an automation. All fields are optional (admin only). Org-scoped: admins can only update automations they own or that belong to their org.

**Request body:**
```json
{
  "name": "Updated name",
  "sql_queries": ["SELECT COUNT(*) FROM transactions WHERE is_fraud = 1"],
  "schedule_preset": "weekly",
  "workflow_graph": null
}
```

---

### DELETE /api/automations/{id}

Delete an automation and remove it from the scheduler (admin only).

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

### PATCH /api/automations/{id}/toggle

Toggle an automation on or off (admin only). When toggled on, the scheduler job is resumed or re-added. When toggled off, the job is paused.

**Response** `200 OK` -- the updated automation object.

---

### POST /api/automations/{id}/run

Trigger a manual run immediately (admin only).

**Response** `200 OK`:
```json
{
  "status": "ok",
  "message": "Manual run triggered for 'Daily Fraud Alert'",
  "run": {
    "id": "run-xyz",
    "automation_id": "auto-abc",
    "status": "success",
    "result_json": {"fraud_count": 45},
    "row_count": 1,
    "execution_time_ms": 234,
    "triggers_fired": [],
    "error_message": null,
    "created_at": "2024-01-15T14:30:00"
  }
}
```

---

### GET /api/automations/{id}/runs

List run history for an automation (admin only).

**Query parameters:**
- `limit` -- Number of runs to return (1--100, default: 20)

**Response** `200 OK` -- array of run objects.

---

### GET /api/automations/{id}/runs/{run_id}

Get a specific run (admin only).

**Response** `200 OK` -- single run object.

---

## Notification Endpoints

**Prefix:** `/api/notifications`

### GET /api/notifications

Get the current user's own notifications.

**Auth:** Any authenticated user.

**Query parameters:**
- `unread_only` -- If `true`, return only unread notifications (default: `false`)

**Response** `200 OK` -- array of notification objects:
```json
[
  {
    "id": "notif-abc",
    "user_id": "user-xyz",
    "automation_id": "auto-abc",
    "run_id": "run-xyz",
    "title": "Alert: Daily Fraud Alert triggered",
    "message": "fraud_count (145) exceeded threshold (100)",
    "severity": "warning",
    "is_read": false,
    "automation_name": "Daily Fraud Alert",
    "created_at": "2024-01-15T09:00:02"
  }
]
```

---

### GET /api/notifications/all

Get notifications scoped by admin role. Org admins see their org's notifications (with user info); super admins see all notifications across the platform (with user info).

**Auth:** Admin required.

**Query parameters:**
- `unread_only` -- Filter to unread only (default: `false`)

---

### GET /api/notifications/count

Get the current user's unread notification count.

**Auth:** Any authenticated user.

**Response** `200 OK`:
```json
{"count": 3}
```

---

### PATCH /api/notifications/{id}/read

Mark a single notification as read (own notifications only).

**Auth:** Any authenticated user.

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Errors:** `404 Not Found`

---

### POST /api/notifications/mark-all-read

Mark all of the current user's notifications as read.

**Auth:** Any authenticated user.

**Response** `200 OK`:
```json
{"status": "ok", "count": 3}
```

---

## Trigger Template Endpoints

**Prefix:** `/api/trigger-templates` (admin only)

Reusable trigger condition sets.

### GET /api/trigger-templates

List all trigger templates. Org admins see templates in their org; super admins see all.

**Auth:** Admin required.

### POST /api/trigger-templates

Create a trigger template.

**Auth:** Admin required.

**Request body:**
```json
{
  "name": "High Volume Alert",
  "description": "Fires when transaction count exceeds threshold",
  "conditions": [
    {"type": "threshold", "column": "count", "operator": "gt", "value": 1000}
  ]
}
```

### PUT /api/trigger-templates/{id}

Update a trigger template. All fields optional. Org-scoped: admins can only update templates they own.

**Auth:** Admin required.

### DELETE /api/trigger-templates/{id}

Delete a trigger template. Org-scoped: admins can only delete templates they own.

**Auth:** Admin required.

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

## Insights Endpoints

**Prefix:** `/api/insights`

Insights are synthesized AI-generated findings saved from enriched chat responses. They can also be created manually from any assistant message.

### POST /api/insights

Create a manual insight from an assistant message.

**Auth:** Any authenticated user.

**Request body:**
```json
{
  "message_id": "msg002",
  "user_note": "Important pattern to watch"
}
```

**Response** `200 OK`:
```json
{"status": "ok", "insight_id": "insight-abc"}
```

**Errors:** `404 Not Found` -- message not found

---

### GET /api/insights

List the current user's insights (paginated).

**Auth:** Any authenticated user.

**Query parameters:**
- `limit` -- Number of insights (1--100, default: 20)
- `offset` -- Pagination offset (default: 0)
- `bookmarked` -- If `true`, return only bookmarked insights (default: `false`)

**Response** `200 OK` -- array of insight objects.

---

### GET /api/insights/all

Admin-scoped insights list (admin only).

**Auth:** Admin required.

**Query parameters:** Same as `GET /api/insights`.

---

### GET /api/insights/count

Return the current user's total insight count (for badge display).

**Auth:** Any authenticated user.

**Response** `200 OK`:
```json
{"count": 12}
```

---

### GET /api/insights/{id}

Get a single insight detail.

**Auth:** Any authenticated user.

**Response** `200 OK` -- insight object with `id`, `title`, `summary`, `content`, `categories`, `bookmarked`, `user_note`, `created_at`.

**Errors:** `404 Not Found`

---

### PATCH /api/insights/{id}/bookmark

Toggle bookmark on an insight.

**Auth:** Any authenticated user.

**Request body:**
```json
{"bookmarked": true}
```

**Response** `200 OK`:
```json
{"status": "ok", "bookmarked": true}
```

---

### DELETE /api/insights/{id}

Delete an insight.

**Auth:** Any authenticated user.

**Response** `200 OK`:
```json
{"status": "ok"}
```

---

## ChatChunk Schema

Every event emitted by `POST /api/chat` is a JSON-serialized `ChatChunk`. All fields except `type`, `conversation_id`, and `timestamp` are optional and only populated for relevant chunk types.

```
ChatChunk {
  type:            string    -- chunk type (see below)
  content?:        string    -- human-readable text content
  sql?:            string    -- SQL query text
  tool_name?:      string    -- name of the tool being called
  args?:           object    -- tool call arguments
  data?:           object    -- type-specific structured payload
  conversation_id: string    -- conversation ID (use for next turn)
  timestamp:       float     -- Unix timestamp
}
```

### Chunk Types

**`status`** -- Progress indicator while the agent is working.
```json
{
  "type": "status",
  "content": "Running SQL analyst...",
  "data": {"agent": "analyst", "phase": "executing"},
  "conversation_id": "abc123",
  "timestamp": 1700000000.0
}
```

**`tool_call`** -- The LLM is invoking a tool.
```json
{
  "type": "tool_call",
  "content": "Calling run_sql with SELECT COUNT(*) FROM transactions",
  "sql": "SELECT COUNT(*) FROM transactions",
  "tool_name": "run_sql",
  "args": {"query": "SELECT COUNT(*) FROM transactions"},
  "data": {"llm_reasoning": "I need to count total transactions first."},
  "conversation_id": "abc123",
  "timestamp": 1700000001.0
}
```

**`sql`** -- A SQL query that was executed.
```json
{
  "type": "sql",
  "sql": "SELECT merchant_category, SUM(amount) FROM transactions GROUP BY merchant_category",
  "conversation_id": "abc123",
  "timestamp": 1700000002.0
}
```

**`tool_result`** -- The result of a tool execution. `data.result` is a JSON string containing `{columns, rows, row_count}` for SQL results. May include chart rendering hints.
```json
{
  "type": "tool_result",
  "data": {
    "tool": "run_sql",
    "result": "{\"columns\":[\"merchant_category\",\"total\"],\"rows\":[...],\"row_count\":10}",
    "visualization": "bar",
    "x_column": "merchant_category",
    "y_column": "total"
  },
  "conversation_id": "abc123",
  "timestamp": 1700000003.0
}
```

**`answer`** -- The final markdown answer from the analyst agent.
```json
{
  "type": "answer",
  "content": "The top 5 merchant categories by total transaction value are:\n\n1. **Food & Dining** -- Rs.45.2M...",
  "conversation_id": "abc123",
  "timestamp": 1700000004.0
}
```

**`insight`** -- A synthesized, cited markdown answer produced by the enrichment orchestrator (agentic mode only). Replaces or follows `answer` in multi-agent responses.
```json
{
  "type": "insight",
  "content": "## Payment Behavior Analysis\n\nBased on 5 independent analyses...",
  "conversation_id": "abc123",
  "timestamp": 1700000010.0
}
```

**`error`** -- An error occurred during processing.
```json
{
  "type": "error",
  "content": "SQL syntax error: no such column 'merchant_name'",
  "conversation_id": "abc123",
  "timestamp": 1700000005.0
}
```

**`clarification`** -- The LLM is asking the user a clarifying question before proceeding (only when `clarification_enabled` is true and `skip_clarification` is false).
```json
{
  "type": "clarification",
  "content": "Do you want to see this breakdown by city or by merchant category?",
  "data": {"skip_allowed": true},
  "conversation_id": "abc123",
  "timestamp": 1700000001.0
}
```

**`metrics`** -- Token usage and timing for the completed response. Always the last chunk before `[DONE]`.
```json
{
  "type": "metrics",
  "data": {
    "input_tokens": 4321,
    "output_tokens": 876,
    "generation_time_ms": 3241
  },
  "conversation_id": "abc123",
  "timestamp": 1700000011.0
}
```

**`orchestrator_plan`** -- The multi-agent orchestrator's reasoning and task decomposition (agentic mode only).
```json
{
  "type": "orchestrator_plan",
  "data": {
    "reasoning": "This question requires three independent analyses: volume by city, by type, and temporal trend.",
    "tasks": [
      {
        "id": "task-1",
        "agent": "analyst",
        "task": "Calculate total transaction volume by city",
        "depends_on": [],
        "category": "geographic"
      },
      {
        "id": "task-2",
        "agent": "analyst",
        "task": "Break down by transaction type",
        "depends_on": [],
        "category": "segmentation"
      }
    ]
  },
  "conversation_id": "abc123",
  "timestamp": 1700000001.5
}
```

**`agent_trace`** -- Execution trace for a single orchestrator sub-task.
```json
{
  "type": "agent_trace",
  "data": {
    "task_id": "task-1",
    "agent": "analyst",
    "category": "geographic",
    "task": "Calculate total transaction volume by city",
    "final_sql": "SELECT city, SUM(amount) FROM transactions GROUP BY city",
    "final_answer": "Mumbai leads with Rs.2.1B in total volume...",
    "success": true,
    "steps": [
      {
        "type": "tool_call",
        "tool": "run_sql",
        "sql": "SELECT city, SUM(amount) FROM transactions GROUP BY city",
        "result_preview": "{\"columns\":[\"city\",\"total\"],\"rows\":[...]}"
      }
    ]
  },
  "conversation_id": "abc123",
  "timestamp": 1700000005.0
}
```

**`enrichment_trace`** -- Execution trace for an enrichment sub-task (legacy agentic mode path).
```json
{
  "type": "enrichment_trace",
  "data": {
    "source_index": 0,
    "category": "temporal",
    "question": "What is the monthly trend?",
    "final_sql": "SELECT strftime('%Y-%m', timestamp) AS month, COUNT(*) FROM transactions GROUP BY month",
    "final_answer": "Transaction volume peaks in December...",
    "steps": [...]
  },
  "conversation_id": "abc123",
  "timestamp": 1700000007.0
}
```

**`stats_context`** -- Pre-computed dataset statistics injected into the response for context (when `stats_context_injection` is enabled).
```json
{
  "type": "stats_context",
  "content": "| Metric | Value |\n|---|---|\n| Total Transactions | 250,000 |...",
  "data": {
    "groups": {
      "by_type": {"P2P": {"count": 125000}, "P2M": {"count": 125000}}
    }
  },
  "conversation_id": "abc123",
  "timestamp": 1700000000.5
}
```
