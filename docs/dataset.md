# Dataset Documentation

## Overview

InsightXpert supports multiple datasets and document uploads. Users can query the default transactions dataset or upload their own CSV files and PDF documents to create new queryable datasets with contextual reference material.

The system ships with a default dataset of 250,000 synthetic Indian digital payment transactions. The dataset models UPI-era payment patterns across multiple transaction types, banks, states, age groups, devices, and network types. It spans the full calendar year 2023 (2023-01-01 to 2023-12-31).

---

## Dataset Management

### Multi-Dataset Architecture

Datasets are stored as metadata records in the `datasets` table (auth database). Each dataset has:

- **DDL** -- the `CREATE TABLE` statement for its data table in the local SQLite database.
- **Documentation** -- rich markdown describing columns, domain values, and statistics, injected into the LLM context.
- **Column metadata** -- per-column type, description, domain values, and domain rules stored in the `dataset_columns` table.
- **Example queries** -- question/SQL pairs stored in the `example_queries` table, used for RAG training.
- **Active flag** -- only one dataset is active at a time. The active dataset determines which table the agent queries and which documentation is injected into the LLM context.

### ORM Models

Defined in `backend/src/insightxpert/auth/models.py`:

| Model | Table | Purpose |
|---|---|---|
| `Dataset` | `datasets` | Dataset metadata: name, description, DDL, documentation, active flag, ownership |
| `DatasetColumn` | `dataset_columns` | Per-column metadata: name, type, description, domain values/rules, ordinal position |
| `ExampleQuery` | `example_queries` | Question/SQL training pairs linked to a dataset |

Key fields on `Dataset`:
- `created_by` -- `NULL` for the seeded default dataset, user ID for uploaded datasets.
- `r2_key` -- Cloudflare R2 object key for the uploaded CSV backup (set after fire-and-forget upload).
- `is_active` -- only one dataset is active at a time.
- `organization_id` -- optional FK to `organizations`.

### Visibility and Access Control

- **System datasets** (`created_by IS NULL`) are visible to all authenticated users.
- **User-uploaded datasets** are scoped to the uploader. Only the owner and super admins (admin with no org) can see, activate, confirm, or delete them.
- **The default transactions dataset cannot be deleted.**
- When a user-uploaded dataset is deleted and it was the active dataset, the system automatically re-activates the default dataset.

---

## CSV Upload Flow

Any authenticated user can upload a CSV file to create a new queryable dataset. The flow is a two-step process: upload, then review and confirm.

### Step 1: Upload

**Endpoint:** `POST /api/datasets/upload`

Accepts a multipart form with:
- `file` -- the CSV file (max 50 MB, `.csv` extension required)
- `name` -- dataset name (must be unique)
- `description` -- optional description

The server:
1. Validates the file extension and size.
2. Parses the CSV with `pandas.read_csv`.
3. Runs the **dataset profiler** (`datasets/profiler.py`) to analyze column types, cardinality, null rates, and sample values.
4. Sanitizes column names (lowercased, underscores, no special characters).
5. Generates a `CREATE TABLE` DDL from the profiled types.
6. Creates the SQLite table and loads data via `pandas.to_sql`.
7. Persists `Dataset` and `DatasetColumn` records in the auth database.
8. Fires a background R2 backup of the raw CSV (if R2 is configured).
9. Returns the dataset metadata with the full `profile` object.

The dataset is created **inactive** -- it becomes active only after confirmation.

### Step 2: Review and Confirm

**Endpoint:** `POST /api/datasets/{dataset_id}/confirm`

Accepts a JSON body with:
- `column_descriptions` -- user-provided descriptions keyed by column name.
- `profile` -- the profile object returned from the upload step.

The server:
1. Merges user-provided descriptions with profiler statistics.
2. Compiles rich documentation markdown (table name, row count, column details table with types, distinct counts, and descriptions).
3. Updates `DatasetColumn` records with user descriptions and domain values.
4. Stores the compiled documentation on the `Dataset` record.
5. Auto-activates the confirmed dataset (deactivates all others).

### Frontend Components

**`csv-upload-dialog.tsx`** -- a two-step dialog component:
- **Upload step:** File picker (drag-to-select), dataset name input, optional description. Auto-fills the name from the file name.
- **Review step:** Displays a profile summary (row count, column count) and a scrollable table of all columns showing: column name, inferred type (color-coded badge), distinct count, detail summary (unique values for low-cardinality columns, numeric range for numbers), and an editable description field. Smart default descriptions are generated from the profile. The user can edit descriptions and confirm.

**`dataset-selector.tsx`** -- a dropdown in the navigation bar:
- Lists all datasets visible to the current user.
- Shows the active dataset with a checkmark.
- Clicking a dataset activates it via `POST /api/datasets/{id}/activate`.
- Eye icon opens the dataset viewer.
- Trash icon (visible for owners and admins) deletes the dataset.
- "Upload CSV" button opens the CSV upload dialog.
- Listens for `dataset-changed` custom events to update state immediately when a dataset is confirmed from any component.

**`dataset-viewer.tsx`** -- a full-screen dialog with two tabs:
- **Data tab:** Paginated read-only view of the dataset (100 rows per page) with row numbers, pagination controls, and CSV export. Executes `SELECT * FROM <table> LIMIT 100 OFFSET <n>` via the `/api/sql/execute` endpoint.
- **Columns tab:** Lazy-loaded column metadata showing column name, type badge, domain values as chips, description, and domain rules.

---

## PDF Document Upload

Users can upload PDF documents as contextual reference material. The extracted text is injected into the LLM context to enrich the agent's understanding of the data domain.

### Upload Flow

**Endpoint:** `POST /api/documents/upload`

Accepts a multipart form with:
- `file` -- the PDF file (max 20 MB, `.pdf` extension required)
- `name` -- document name
- `description` -- optional description
- `dataset_id` -- optional FK linking the document to a specific dataset

The server:
1. Validates the file extension and size.
2. Extracts text via `pypdf.PdfReader` (`storage/pdf_extractor.py`). Produces page-delimited text with `--- Page N ---` markers.
3. Detects scanned PDFs (no extractable text) and adds a warning message.
4. Fires a background R2 upload of the raw PDF (if R2 is configured).
5. Creates a `Document` record in the auth database with the extracted text, page count, and file metadata.
6. Returns the document metadata with a text preview (first 500 characters).

### Document Context Injection

`DocumentService.get_documents_context_markdown()` builds a markdown section from all uploaded documents (optionally filtered by `dataset_id`). This is injected into the LLM system prompt as `## Uploaded Reference Documents` with per-document headings and extracted text.

### Other Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/documents` | Any user | List documents visible to the current user |
| `DELETE` | `/api/documents/{doc_id}` | Owner or admin | Delete a document and clean up R2 |

### Frontend Component

**`pdf-upload-dialog.tsx`** -- a dialog with:
- File picker for PDFs (max 20 MB).
- Name and optional description inputs.
- After successful upload, shows a confirmation view with page count and a scrollable preview of the extracted text.

### Frontend Types

Defined in `frontend/src/types/dataset.ts`:

```typescript
interface DatasetInfo {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  table_name: string | null;
  organization_id?: string | null;
  created_by: string | null;
}

interface DocumentInfo {
  id: string;
  name: string;
  description: string | null;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  page_count: number;
  extracted_text_preview: string | null;
  dataset_id: string | null;
  created_by: string;
  created_at: string;
}
```

---

## Dataset Profiler

`backend/src/insightxpert/datasets/profiler.py` provides pure computational DataFrame profiling with no database or API dependencies.

### `profile_dataframe(df) -> dict`

Analyzes a pandas DataFrame and returns:

```python
{
    "row_count": int,
    "column_count": int,
    "columns": [
        {
            "name": str,             # sanitized column name
            "original_name": str,    # raw CSV header
            "inferred_type": str,    # INTEGER, REAL, TEXT, BOOLEAN, DATETIME
            "distinct_count": int,
            "null_count": int,
            "null_percent": float,
            "is_unique": bool,       # every non-null value appears exactly once
            "cardinality": str,      # "unique", "high", "medium", "low"
            "unique_values": list | None,  # sorted values if distinct_count <= 50
            "min": float | None,     # for numeric columns
            "max": float | None,
            "mean": float | None,
        },
        ...
    ]
}
```

### Type Inference

The profiler maps pandas dtypes to SQLite-friendly types:

| pandas dtype | Inferred type |
|---|---|
| `bool` | `BOOLEAN` |
| `int*` | `INTEGER` |
| `float*` | `REAL` |
| `datetime64` | `DATETIME` |
| `object`/`string` with boolean-like pairs (`true/false`, `yes/no`, `0/1`, `y/n`, `t/f`) | `BOOLEAN` |
| `object`/`string` where >= 90% of values parse as datetimes | `DATETIME` |
| Everything else | `TEXT` |

### Cardinality Classification

| Cardinality | Rule |
|---|---|
| `unique` | `distinct_count == row_count` |
| `high` | ratio > 0.5 |
| `medium` | ratio > 0.05 |
| `low` | ratio <= 0.05 |

### Column Name Sanitization

Raw CSV headers are converted to safe SQLite column names: lowercased, non-alphanumeric characters replaced with underscores, consecutive underscores collapsed, leading/trailing underscores stripped. Empty results default to `"col"`.

---

## Dataset Dependencies

`backend/src/insightxpert/datasets/dependencies.py` provides FastAPI dependency injection for resolving user roles in dataset endpoints.

### `ResolvedUser`

A dataclass bundling the authenticated user with their computed role flags:

```python
@dataclass
class ResolvedUser:
    user: User
    is_admin: bool
    is_super_admin: bool  # admin with no org
```

### `resolve_user_roles`

A FastAPI dependency that resolves the current user and checks admin status against the configured admin domains. Used by dataset endpoints that need ownership or admin checks.

---

## Storage Backend (Cloudflare R2)

`backend/src/insightxpert/storage/r2.py` provides a best-effort object storage service using Cloudflare R2 via the S3-compatible API (boto3).

### `R2StorageService`

All methods are synchronous -- callers use `asyncio.to_thread()`.

| Method | Description |
|---|---|
| `upload_file(key, content, content_type)` | Upload bytes to R2. Returns `True` on success. |
| `delete_file(key)` | Delete an object. Returns `True` on success. |
| `generate_presigned_url(key, expires_in)` | Generate a presigned GET URL (default 1 hour). Returns `None` on failure. |

### Configuration

Requires four values (typically from environment variables):
- `access_key_id` -- R2 access key
- `secret_access_key` -- R2 secret key
- `endpoint_url` -- R2 endpoint (e.g. `https://<account_id>.r2.cloudflarestorage.com`)
- `bucket` -- R2 bucket name

### R2 Key Patterns

| Upload type | Key format |
|---|---|
| CSV dataset | `uploads/{user_id}/{dataset_id}/{filename}` |
| PDF document | `documents/{user_id}/{doc_id}/{filename}` |

R2 uploads and deletes are always fire-and-forget -- they do not block the API response. Failures are logged but do not cause request errors.

---

## Dataset Service

`backend/src/insightxpert/datasets/service.py` provides the `DatasetService` class that handles all dataset CRUD, CSV ingestion, and documentation compilation.

### Key Methods

| Method | Description |
|---|---|
| `get_active_dataset()` | Returns the currently active dataset (cached with 60s TTL). |
| `get_dataset_by_id(id)` | Returns a single dataset dict. |
| `list_datasets(user_id, is_super_admin)` | Returns datasets visible to the caller with user-scope filtering. |
| `get_dataset_columns(id)` | Returns column metadata ordered by ordinal position. |
| `get_example_queries(id)` | Returns active example queries. |
| `get_dataset_ddl(id)` | Returns the DDL string. |
| `get_dataset_documentation(id)` | Returns the documentation string. |
| `build_documentation_markdown(id)` | Builds documentation markdown from DB column metadata. |
| `create_dataset_from_csv(...)` | Parses CSV, profiles it, creates SQLite table, persists metadata. |
| `confirm_dataset(...)` | Merges user descriptions with profile, compiles documentation, auto-activates. |
| `activate_dataset(id)` | Sets one dataset as active, deactivates all others. |
| `update_dataset(id, **fields)` | Updates dataset fields (name, description, DDL, documentation). |
| `delete_dataset(id, user_id, is_admin)` | Drops the data table, deletes related records, re-activates default if needed. |
| `add_column(id, ...)` | Adds a column metadata entry. |
| `update_column(id, col_id, ...)` | Updates a column metadata entry. |
| `add_example_query(id, ...)` | Adds an example query. |
| `delete_example_query(id, query_id)` | Deletes an example query. |

---

## Dataset Routes

`backend/src/insightxpert/datasets/routes.py` -- mounted at `/api/datasets`.

### Public Endpoints (any authenticated user)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/datasets/public` | List datasets visible to the current user |
| `GET` | `/api/datasets/public/{id}/columns` | Get column metadata for a dataset (user-scoped) |
| `POST` | `/api/datasets/upload` | Upload a CSV to create a new dataset |
| `POST` | `/api/datasets/{id}/confirm` | Confirm a dataset with column descriptions |
| `POST` | `/api/datasets/{id}/activate` | Activate a dataset |
| `DELETE` | `/api/datasets/{id}` | Delete a dataset (owner or admin) |

### Admin Endpoints (super admin only)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/datasets` | List all datasets |
| `GET` | `/api/datasets/{id}` | Get dataset with columns and example queries |
| `PUT` | `/api/datasets/{id}` | Update dataset metadata |
| `POST` | `/api/datasets/{id}/columns` | Add column metadata |
| `PUT` | `/api/datasets/{id}/columns/{col_id}` | Update column metadata |
| `POST` | `/api/datasets/{id}/queries` | Add example query |
| `DELETE` | `/api/datasets/{id}/queries/{query_id}` | Delete example query |
| `POST` | `/api/datasets/{id}/retrain` | Re-run RAG training for a dataset |

---

## Default Dataset: UPI Transactions

### Table Schema

```sql
CREATE TABLE transactions (
    transaction_id     TEXT PRIMARY KEY,
    timestamp          TEXT NOT NULL,
    transaction_type   TEXT NOT NULL,
    amount_inr         REAL NOT NULL,
    transaction_status TEXT NOT NULL,
    merchant_category  TEXT,
    sender_bank        TEXT NOT NULL,
    receiver_bank      TEXT NOT NULL,
    sender_state       TEXT NOT NULL,
    sender_age_group   TEXT NOT NULL,
    receiver_age_group TEXT,
    device_type        TEXT NOT NULL,
    network_type       TEXT NOT NULL,
    fraud_flag         INTEGER NOT NULL DEFAULT 0,
    hour_of_day        INTEGER NOT NULL,
    day_of_week        TEXT NOT NULL,
    is_weekend         INTEGER NOT NULL DEFAULT 0
);
```

### Column Descriptions

| Column | Type | Description |
|---|---|---|
| `transaction_id` | TEXT | Unique UUID per transaction. Primary key. |
| `timestamp` | TEXT | ISO 8601 datetime string. Covers 2023-01-01 to 2023-12-31. |
| `transaction_type` | TEXT | `P2P`, `P2M`, `Bill Payment`, or `Recharge` |
| `amount_inr` | REAL | Transaction amount in Indian Rupees (INR). |
| `transaction_status` | TEXT | `SUCCESS`, `FAILED`, or `PENDING` |
| `merchant_category` | TEXT | Category of the merchant. NULL for P2P transactions. Values: `Food`, `Grocery`, `Fuel`, `Entertainment`, `Shopping`, `Healthcare`, `Education`, `Transport`, `Utilities`, `Other` |
| `sender_bank` | TEXT | Sending bank. Values: HDFC, SBI, ICICI, Axis, Kotak, Yes, PNB, BOB, Union, Canara |
| `receiver_bank` | TEXT | Receiving bank. Same set of values as `sender_bank`. |
| `sender_state` | TEXT | Indian state of the sender. All 28 states and 8 union territories are represented. |
| `sender_age_group` | TEXT | Age bracket of the sender: `18-25`, `26-35`, `36-45`, `46-55`, `55+` |
| `receiver_age_group` | TEXT | Age bracket of the receiver. Same categories. May be NULL for merchant-side receivers. |
| `device_type` | TEXT | Device used to initiate the transaction: `Android`, `iOS`, `Web` |
| `network_type` | TEXT | Network at time of transaction: `4G`, `5G`, `WiFi`, `3G` |
| `fraud_flag` | INTEGER | `0` = not flagged. `1` = flagged for review. This is **not confirmed fraud** -- it is a risk signal. |
| `hour_of_day` | INTEGER | Hour extracted from `timestamp`. Range 0-23. |
| `day_of_week` | TEXT | Day name extracted from `timestamp` (e.g. `Monday`, `Tuesday`, ...). |
| `is_weekend` | INTEGER | `1` if Saturday or Sunday, `0` otherwise. |

### Indices

Nine indices are created by `generate_data.py` after loading:

| Index name | Column(s) |
|---|---|
| `idx_txn_type` | `transaction_type` |
| `idx_status` | `transaction_status` |
| `idx_merchant` | `merchant_category` |
| `idx_sender_bank` | `sender_bank` |
| `idx_device` | `device_type` |
| `idx_fraud` | `fraud_flag` |
| `idx_hour` | `hour_of_day` |
| `idx_weekend` | `is_weekend` |
| `idx_state` | `sender_state` |

---

## Pre-Computed Statistics

On first startup, `db/stats_computer.py` computes summary statistics from the transactions table and stores them in the `dataset_stats` table in the auth database. This computation is idempotent -- if `dataset_stats` already has rows, it exits immediately.

These stats are injected into the LLM context as a `stats_context` chunk when `stats_context_injection` is enabled (admin feature toggle).

Statistics groups and metrics computed:

| Group | Dimension | Metrics |
|---|---|---|
| `overall` | -- | `txn_count`, `date_min`, `date_max`, `avg_amount`, `failure_rate_pct`, `fraud_rate_pct`, `failure_count`, `fraud_count` |
| `transaction_type` | per `transaction_type` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `merchant_category` | per `merchant_category` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `bank` | per `sender_bank` | `txn_count`, `avg_amount_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `state` | per `sender_state` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `age_group` | per `sender_age_group` | `txn_count`, `avg_amount_inr`, `failure_count`, `failure_rate_pct` |
| `device_type` | per `device_type` | `txn_count`, `failure_count`, `failure_rate_pct`, `fraud_count`, `fraud_rate_pct` |
| `network_type` | per `network_type` | `txn_count`, `failure_count`, `failure_rate_pct` |
| `monthly` | per `YYYY-MM` | `txn_count`, `avg_amount_inr`, `total_volume_inr`, `failure_count`, `fraud_count` |
| `hourly` | per `hour_of_day` | `txn_count`, `failure_count`, `fraud_count` |

---

## Loading the Default Dataset

```bash
cd backend
python generate_data.py
```

This script:

1. Drops and recreates the `transactions` table (other tables such as `users`, `conversations`, `dataset_stats` are preserved).
2. Reads `upi_transactions_2024.csv` in 10,000-row batches and inserts via `executemany`.
3. Creates all 9 indices.

The script prints row count progress and a final total.

---

## Example Queries

These are the question/SQL pairs used as RAG training examples in `training/queries.py`. They cover all six challenge categories.

### Descriptive

**Average transaction amount for bill payments**
```sql
SELECT AVG(amount_inr) AS avg_amount
FROM transactions
WHERE transaction_type = 'Bill Payment';
```

**Overall transaction count and success rate**
```sql
SELECT
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS success_rate_pct
FROM transactions;
```

### Comparative

**Failure rate comparison: Android vs iOS**
```sql
SELECT
    device_type,
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM transactions
WHERE device_type IN ('Android', 'iOS')
GROUP BY device_type;
```

**Average transaction amount by type**
```sql
SELECT
    transaction_type,
    AVG(amount_inr) AS avg_amount,
    COUNT(*) AS txn_count
FROM transactions
GROUP BY transaction_type
ORDER BY avg_amount DESC;
```

### Temporal

**Peak transaction hours for food delivery**
```sql
SELECT hour_of_day, COUNT(*) AS txn_count
FROM transactions
WHERE merchant_category = 'Food'
GROUP BY hour_of_day
ORDER BY txn_count DESC
LIMIT 5;
```

**Weekend vs weekday transaction volume and amounts**
```sql
SELECT
    CASE WHEN is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    COUNT(*) AS txn_count,
    AVG(amount_inr) AS avg_amount
FROM transactions
GROUP BY is_weekend;
```

### Segmentation

**Age groups most active in P2P transfers**
```sql
SELECT sender_age_group, COUNT(*) AS p2p_count
FROM transactions
WHERE transaction_type = 'P2P'
GROUP BY sender_age_group
ORDER BY p2p_count DESC;
```

**State-wise transaction volume (top 10)**
```sql
SELECT
    sender_state,
    COUNT(*) AS txn_count,
    SUM(amount_inr) AS total_amount
FROM transactions
GROUP BY sender_state
ORDER BY txn_count DESC
LIMIT 10;
```

### Correlation

**Network type vs transaction success rate**
```sql
SELECT
    network_type,
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS success_rate_pct,
    SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM transactions
GROUP BY network_type
ORDER BY success_rate_pct DESC;
```

**High-value vs low-value transaction failure rates**
```sql
SELECT
    CASE
        WHEN amount_inr >= 10000 THEN 'High (>=10K)'
        WHEN amount_inr >= 1000  THEN 'Medium (1K-10K)'
        ELSE 'Low (<1K)'
    END AS amount_bucket,
    COUNT(*) AS total_txns,
    SUM(CASE WHEN transaction_status = 'FAILED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS failure_rate_pct
FROM transactions
GROUP BY amount_bucket
ORDER BY failure_rate_pct DESC;
```

### Risk Analysis

**Fraud flag rate for high-value transactions**
```sql
SELECT
    COUNT(*) AS high_value_txns,
    SUM(fraud_flag) AS flagged_count,
    SUM(fraud_flag) * 100.0 / COUNT(*) AS flagged_pct
FROM transactions
WHERE amount_inr >= 10000;
```

**Bank x device fraud-flag concentration during late-night weekends**
```sql
WITH late_night_weekend AS (
    SELECT
        sender_bank,
        device_type,
        COUNT(*) AS total_txns,
        SUM(fraud_flag) AS flagged_txns,
        SUM(fraud_flag) * 1.0 / COUNT(*) AS flag_rate
    FROM transactions
    WHERE hour_of_day IN (22, 23, 0, 1, 2, 3) AND is_weekend = 1
    GROUP BY sender_bank, device_type
),
baseline AS (
    SELECT
        sender_bank,
        device_type,
        COUNT(*) AS total_txns,
        SUM(fraud_flag) AS flagged_txns,
        SUM(fraud_flag) * 1.0 / COUNT(*) AS baseline_flag_rate
    FROM transactions
    GROUP BY sender_bank, device_type
)
SELECT
    l.sender_bank,
    l.device_type,
    l.total_txns AS late_night_wknd_txns,
    l.flag_rate AS late_night_wknd_flag_rate,
    b.baseline_flag_rate,
    l.flag_rate / NULLIF(b.baseline_flag_rate, 0) AS risk_ratio
FROM late_night_weekend l
JOIN baseline b ON l.sender_bank = b.sender_bank AND l.device_type = b.device_type
ORDER BY risk_ratio DESC;
```

---

## File Reference

### Backend

| File | Purpose |
|---|---|
| `backend/src/insightxpert/datasets/routes.py` | Dataset API routes (upload, confirm, activate, CRUD, retrain) |
| `backend/src/insightxpert/datasets/service.py` | `DatasetService` -- CRUD, CSV ingestion, documentation compilation |
| `backend/src/insightxpert/datasets/profiler.py` | `profile_dataframe()` -- pure computational DataFrame profiling |
| `backend/src/insightxpert/datasets/dependencies.py` | `ResolvedUser` dataclass and `resolve_user_roles` FastAPI dependency |
| `backend/src/insightxpert/storage/r2.py` | `R2StorageService` -- Cloudflare R2 object storage via boto3 |
| `backend/src/insightxpert/storage/document_service.py` | `DocumentService` -- PDF document CRUD and LLM context builder |
| `backend/src/insightxpert/storage/pdf_extractor.py` | `extract_text_from_pdf()` -- pypdf text extraction |
| `backend/src/insightxpert/storage/routes.py` | Document API routes (upload, list, delete) |
| `backend/src/insightxpert/auth/models.py` | ORM models: `Dataset`, `DatasetColumn`, `ExampleQuery` |

### Frontend

| File | Purpose |
|---|---|
| `frontend/src/components/dataset/csv-upload-dialog.tsx` | Two-step CSV upload dialog (upload + profile review) |
| `frontend/src/components/dataset/pdf-upload-dialog.tsx` | PDF upload dialog with text extraction preview |
| `frontend/src/components/dataset/dataset-viewer.tsx` | Full-screen dataset viewer (data table + column metadata) |
| `frontend/src/components/layout/dataset-selector.tsx` | Navbar dropdown for switching, viewing, uploading, and deleting datasets |
| `frontend/src/types/dataset.ts` | TypeScript types: `DatasetInfo`, `DocumentInfo` |

---

## Important Caveats

- **Synthetic data.** All 250,000 rows in the default dataset were generated programmatically. Patterns are statistically plausible for Indian UPI payments but are not derived from real transactions. Insights are directional, not predictive.

- **`fraud_flag = 1` does not mean confirmed fraud.** It means the transaction was flagged for review based on risk heuristics in the data generator. Treat it as a risk signal, not a label.

- **Correlation only.** No causal relationships are present. Associations between columns (e.g. 5G and higher success rates) reflect the generation model, not real-world causality.

- **No individual user IDs.** The default dataset contains no unique sender/receiver identifiers beyond `sender_bank`, `sender_state`, and `sender_age_group`. There is no way to track individual user behaviour across transactions.

- **CSV upload memory.** `pandas.read_csv` loads the entire file into memory. At the 50 MB limit, the DataFrame can be 3-5x the raw size (~150-250 MB). Concurrent uploads can spike memory.

- **R2 is best-effort.** R2 uploads and deletes are fire-and-forget. Failures are logged but do not cause request errors. The dataset remains functional without R2.

- **PDF text extraction limitations.** Scanned PDFs without OCR will not yield extractable text. The system detects this and adds a warning message.
