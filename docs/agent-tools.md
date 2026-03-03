# InsightXpert Agent Tools Reference

## Overview

InsightXpert uses a multi-mode orchestrator pipeline with the following agents:

| Agent | Used In | Purpose |
|---|---|---|
| **Clarifier** | All modes (optional) | Pre-check: decides if the question needs clarification before SQL generation |
| **Analyst** | All modes | Core text-to-SQL loop -- queries the DB and produces a natural-language answer |
| **Orchestrator** | `agentic` mode | Evaluates analyst output, plans enrichment tasks, synthesizes cited insights |
| **Quant Analyst** | `agentic`, `deep` | Quantitative analysis on upstream SQL results (stats + advanced tools) |
| **Deep Think** | `deep` mode | 5W1H dimensional analysis with auto-investigation |

### Pipeline Modes

- **`basic`** -- Analyst only. Direct SQL generation and answer; no orchestration.
- **`agentic`** -- Analyst runs first (user sees results immediately), then an evaluator decides if enrichment is needed. If yes, additional targeted tasks run via DAG execution, and a synthesizer combines everything into a cited insight.
- **`deep`** -- 5W1H dimensional analysis. Extracts WHO/WHAT/WHEN/WHERE/HOW dimensions in parallel with the analyst, then runs targeted enrichment tasks, synthesizes a dimensional insight, and auto-investigates gaps.

---

## Clarifier

No tools -- makes a single lightweight LLM call to detect ambiguous questions.

**Outputs:** `{ "action": "execute" }` or `{ "action": "clarify", "question": "..." }`

---

## Analyst Tools

The analyst uses these tools in its agentic loop. The default registry includes `run_sql`, `get_schema`, and `search_similar`. The `clarify` tool is conditionally registered when clarification is enabled.

### `run_sql`
Execute a SQL SELECT query against the connected database.

| Arg | Type | Required | Description |
|---|---|---|---|
| `sql` | string | yes | SQL query to execute |
| `visualization` | enum | no | Chart type: `bar`, `pie`, `line`, `grouped-bar`, `table` |
| `x_column` | string | no | Column to use as x-axis / categories |
| `y_column` | string | no | Column to use as y-axis / values |

**Returns:** `{ "rows": [...], "row_count": N }`

---

### `get_schema`
Get the CREATE TABLE DDL statements for database tables.

| Arg | Type | Required | Description |
|---|---|---|---|
| `tables` | string[] | no | Specific table names; omit to get all tables |

**Returns:** DDL string (all tables) or array of table info objects (specific tables)

---

### `search_similar`
Search the RAG knowledge base for similar past queries, DDL, or documentation.

| Arg | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Search query text |
| `collection` | enum | yes | `qa_pairs`, `ddl`, or `docs` |

**Returns:** Array of matching items with distance scores

---

### `clarify`
Ask the user a clarifying question when their request is ambiguous. Only registered when clarification is enabled.

| Arg | Type | Required | Description |
|---|---|---|---|
| `question` | string | yes | The clarifying question to ask the user |

**Returns:** `{ "clarification": "..." }`

---

## Quant Analyst Tools

The quant analyst runs as a downstream agent in the multi-agent orchestrator when a sub-task requires quantitative analysis beyond SQL. It receives upstream SQL analyst results as context and operates on them via a combined toolset.

**Registered tools (7):** `run_sql`, `run_python`, `test_hypothesis`, `compute_correlation`, `compute_descriptive_stats`, `score_fraud_risk`, `compute_time_series_slope`.

### `run_python`
Execute a Python snippet for custom statistical analysis. Pre-loaded: `np`, `pd`, `stats` (scipy.stats), `math`, `json`, `itertools`, `collections`, `functools`, `datetime`, `re`, `df` (analyst results as DataFrame).

Sandboxed execution: only standard-library and scientific modules are importable. System modules (`os`, `subprocess`, `sys`) are blocked. Execution times out after 10 seconds (configurable).

| Arg | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | Python code to execute; `print()` output is captured and returned |

**Returns:** `{ "output": "..." }` or `{ "error": "..." }` on failure/timeout

---

### `compute_descriptive_stats`
Compute descriptive statistics for a numeric column.

| Arg | Type | Required | Description |
|---|---|---|---|
| `column` | string | yes | Column name from the analyst results |

**Returns:** `count`, `mean`, `std`, `min`, `q1`, `median`, `q3`, `max`, `skewness`, `kurtosis`

---

### `test_hypothesis`
Run a statistical hypothesis test on the analyst results.

| Arg | Type | Required | Description |
|---|---|---|---|
| `test` | enum | yes | `chi_squared`, `t_test`, `mann_whitney`, `anova`, `z_proportion` |
| `column` | string | varies | Primary numeric column (t_test, mann_whitney, anova) |
| `group_column` | string | varies | Column to split groups (t_test, mann_whitney, anova) |
| `group_a` | string | varies | Value for group A (t_test, mann_whitney) |
| `group_b` | string | varies | Value for group B (t_test, mann_whitney) |
| `category_col_1` | string | chi_squared | First categorical column |
| `category_col_2` | string | chi_squared | Second categorical column |
| `count_column` | string | no | Column containing counts/frequencies (chi_squared only). Use when data is pre-aggregated -- each row is a unique combination with a count. Omit for row-level data. |
| `count_success` | int | z_proportion | Number of successes |
| `count_total` | int | z_proportion | Total trials |
| `hypothesized_proportion` | float | no | H0 proportion for z_proportion (default 0.5) |

**Returns per test:**
- `chi_squared` -- statistic, p_value, dof, effect_size_cramers_v, significant_at_005
- `t_test` -- statistic, p_value, effect_size_cohens_d, group means & sizes, significant_at_005
- `mann_whitney` -- statistic, p_value, effect_size_r, group sizes, significant_at_005
- `anova` -- statistic, p_value, effect_size_eta_squared, num_groups, significant_at_005
- `z_proportion` -- statistic, p_value, observed_proportion, hypothesized_proportion, sample_size, significant_at_005

---

### `compute_correlation`
Compute correlation between two numeric columns.

| Arg | Type | Required | Description |
|---|---|---|---|
| `column_x` | string | yes | First numeric column |
| `column_y` | string | yes | Second numeric column |
| `method` | enum | no | `pearson` (default), `spearman`, `kendall` |

**Returns:** `method`, `correlation`, `p_value`, `n`, `significant_at_005`

---

### `fit_distribution`
Fit statistical distributions to a numeric column and rank by KS-test p-value.
Tries: `normal`, `exponential`, `lognormal`, `gamma`, `weibull_min`.

| Arg | Type | Required | Description |
|---|---|---|---|
| `column` | string | yes | Numeric column to fit |

**Returns:** `best_fit`, `fits` (array ranked by KS p-value with params)

> Note: `fit_distribution` is defined in `stat_tools.py` but not registered in the quant analyst's default registry. It is available when a custom tool registry is used.

---

### `run_sql` *(also available to quant analyst)*
Same as the analyst's `run_sql` -- lets the quant analyst run follow-up queries.

---

## Advanced Analytics Tools

These tools are defined in `advanced_tools.py` and are selectively registered by agents that need them. The quant analyst registers `compute_time_series_slope` and `score_fraud_risk` from this set.

### Time-Series Tools

#### `compute_time_series_slope`
Fit linear regression (scipy.stats.linregress) to a metric over a time/ordinal index.

| Arg | Type | Required | Description |
|---|---|---|---|
| `value_column` | string | yes | Numeric column to fit regression on (y-axis) |
| `time_column` | string | no | Column to use as x-axis; uses row index if omitted |
| `time_unit` | enum | no | Label for the time unit: `day`, `week`, `month` (interpretation text only) |

**Returns:** `slope`, `intercept`, `r_squared`, `p_value`, `std_error`, `ci_95`, `trend_direction`, `interpretation`

---

#### `compute_area_under_curve`
Compute the area under a time-series curve using `numpy.trapz` -- useful for cumulative impact (e.g. total volume over months).

| Arg | Type | Required | Description |
|---|---|---|---|
| `value_column` | string | yes | Numeric column (y-values) |
| `time_column` | string | no | Numeric time column for non-uniform x-axis |

**Returns:** `auc`, `n_points`, `sum`, `mean`, `interpretation`

---

#### `compute_percentage_change`
Compute period-over-period percentage change in a metric series, plus momentum (accelerating vs. decelerating).

| Arg | Type | Required | Description |
|---|---|---|---|
| `value_column` | string | yes | Numeric column |
| `time_column` | string | no | Optional column used only for row ordering (values not used numerically) |
| `lag` | int | no | Number of periods to lag for the comparison (default 1) |

**Returns:** `n_periods`, `lag`, `mean_pct_change`, `std_pct_change`, `min_pct_change`, `max_pct_change`, `periods_positive`, `periods_negative`, `momentum_direction`, `interpretation`

---

#### `detect_peaks`
Detect local peaks (surge periods) in a numeric series using `scipy.signal.find_peaks`.

| Arg | Type | Required | Description |
|---|---|---|---|
| `value_column` | string | yes | Numeric column |
| `time_column` | string | no | Label column for peak positions |
| `num_peaks` | int | no | Max peaks to return (default 5) |
| `min_prominence_ratio` | float | no | Minimum prominence as fraction of value range (0-1, default 0.2). Higher values filter out minor bumps. |

**Returns:** `n_peaks_found`, `top_peaks` (array with index, label, value, surrounding_avg, deviation_from_avg_pct), `interpretation`

---

#### `detect_change_points`
Detect structural change points using variance-minimization (scans all split points, picks minimum within-segment variance), validated with an unpaired t-test.

| Arg | Type | Required | Description |
|---|---|---|---|
| `value_column` | string | yes | Numeric column |
| `time_column` | string | no | Label column for change-point positions |
| `min_segment_size` | int | no | Minimum number of rows in each segment (default 5) |

**Returns:** `n_changepoints`, `changepoints` (array with mean_before, mean_after, pct_change, t_stat, p_value, significant), `interpretation`

---

### Fraud & Risk Tools

#### `score_fraud_risk`
Compute empirical fraud risk lift for multi-dimensional segments.
Lift = segment_fraud_rate / overall_fraud_rate -- high-lift segments are disproportionately fraudulent. Also computes chi-squared contribution per segment.

| Arg | Type | Required | Description |
|---|---|---|---|
| `group_columns` | string[] | yes | Categorical columns to segment by |
| `fraud_column` | string | no | Binary fraud flag column (0/1 or True/False). Default: `fraud_flag` |
| `min_segment_size` | int | no | Minimum rows in a segment to include (default 10) |
| `top_n` | int | no | Return top-N highest-risk segments (default 10) |

**Returns:** `overall_fraud_rate`, `high_risk_segments` (array with fraud_rate, lift, chi2_contribution), `interpretation`

---

#### `detect_amount_anomalies`
Detect anomalous transaction amounts using the Modified Z-score method (Iglewicz & Hoaglin 1993): `M_i = 0.6745*(x_i - median) / MAD`. More robust than mean/std for fat-tailed financial distributions.

| Arg | Type | Required | Description |
|---|---|---|---|
| `amount_column` | string | no | Numeric amount column (default: `amount_inr`) |
| `group_by` | string | no | Optional categorical column to compute anomalies per group |
| `z_threshold` | float | no | Modified Z-score threshold (default 3.5) |

**Returns:** `method`, `z_threshold`, anomaly stats (group_size, anomaly_count, anomaly_rate, median, mad, min/max anomaly amounts). When `group_by` is provided, returns `results_by_group` array.

---

#### `test_temporal_fraud_clustering`
Test whether fraud is uniformly distributed across time periods (hour_of_day, day_of_week, etc.) using a chi-squared goodness-of-fit test. Shannon entropy measures concentration. Significant result = temporal clustering of fraud.

| Arg | Type | Required | Description |
|---|---|---|---|
| `time_column` | string | no | Temporal column (default: `hour_of_day`) |
| `fraud_column` | string | no | Binary fraud flag column (default: `fraud_flag`) |
| `alpha` | float | no | Significance level (default 0.05) |

**Returns:** `total_fraud_cases`, `n_periods`, `chi2_stat`, `p_value`, `significant`, `entropy`, `normalized_entropy`, `peak_periods` (top 5), `interpretation`

---

#### `compute_bank_pair_risk`
Compute fraud risk for each sender_bank x receiver_bank pair. Z-tests each pair's fraud rate against the overall baseline with Bonferroni correction for multiple comparisons.

| Arg | Type | Required | Description |
|---|---|---|---|
| `sender_col` | string | no | Sender bank column (default: `sender_bank`) |
| `receiver_col` | string | no | Receiver bank column (default: `receiver_bank`) |
| `fraud_col` | string | no | Binary fraud flag column (default: `fraud_flag`) |
| `min_pair_size` | int | no | Minimum transactions for a pair to be included (default 5) |
| `top_n` | int | no | Return top-N riskiest pairs (default 5) |

**Returns:** `baseline_fraud_rate`, `n_pairs_evaluated`, `bonferroni_threshold`, `top_riskiest_pairs` (array with fraud_rate, lift, z_score, p_value, significant_after_bonferroni), `interpretation`

---

### General Analytics Tools

#### `compute_percentile_rank`
Rank segments (states, banks, categories) by a numeric metric and assign quartile or decile buckets -- useful for benchmarking and performance tiering.

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column to rank |
| `group_column` | string | yes | Categorical column for segments |
| `n_bins` | enum | no | `4` (quartile, default) or `10` (decile) |

**Returns:** `ranked_segments` (array with group, value, rank, percentile, bucket_label), `interpretation`

---

#### `compute_concentration_index`
Compute the Herfindahl-Hirschman Index (HHI = sum(share_i^2) x 10000).
- 0-1500: competitive
- 1500-2500: moderate concentration
- >2500: highly concentrated

| Arg | Type | Required | Description |
|---|---|---|---|
| `group_column` | string | yes | Categorical column |
| `value_column` | string | no | Numeric weight column; uses row counts if absent |

**Returns:** `hhi`, `interpretation`, `top_3_share_pct`, `n_segments`, `segments` (array with share_pct)

---

#### `test_benford_law`
Test whether transaction amounts conform to Benford's law (expected first-digit distribution: `P(d) = log10(1 + 1/d)`). Significant deviation may indicate data quality issues or synthetic generation artifacts. Requires >= 100 data points.

| Arg | Type | Required | Description |
|---|---|---|---|
| `amount_column` | string | no | Numeric amount column (default: `amount_inr`) |

**Returns:** `n_valid`, `chi2_stat`, `p_value`, `significant`, `digit_distribution` (array with observed_pct, expected_pct, deviation), `interpretation`

---

## RAG Knowledge Base

The RAG module (`rag/store.py`) provides semantic search over four ChromaDB collections used by the analyst and training pipelines.

| Collection | Content | Populated By |
|---|---|---|
| `qa_pairs` | Question-to-SQL pairs | Trainer (curated examples) + analyst auto-save after successful answers |
| `ddl` | CREATE TABLE statements | Trainer from static DDL + live DB introspection |
| `docs` | Business-context documentation | Trainer from `training/documentation.py` |
| `findings` | Anomaly-detection results | Reserved (currently unused) |

**Deduplication:** Documents are keyed by `SHA-256(content)[:16]`. Writes use `upsert`, so duplicate inserts are no-ops.

**Distance metric:** ChromaDB L2 (Euclidean). Lower distance = higher similarity. The analyst pipeline typically filters with `max_distance <= 1.0`.

---

## Non-Agent Features

These features are implemented as standalone API services rather than agent tools.

### Voice Transcription
WebSocket endpoint (`/api/transcribe`) that proxies browser audio to Deepgram Nova-3 for real-time speech-to-text. Requires authentication via JWT (cookie or query param) and a configured `DEEPGRAM_API_KEY`.

- **Protocol:** WebSocket (bidirectional audio/transcript streaming)
- **Model:** Deepgram Nova-3, English, with punctuation and smart formatting
- **Source:** `voice/routes.py`

### Document Storage
PDF upload and management API (`/api/documents`). Uploaded PDFs are text-extracted and stored for LLM context injection via `DocumentService.get_documents_context_markdown()`.

- **Endpoints:** `POST /upload`, `GET /`, `DELETE /{doc_id}`
- **Storage:** Local DB record + optional Cloudflare R2 for file storage
- **Max file size:** 20 MB
- **Source:** `storage/routes.py`, `storage/document_service.py`, `storage/pdf_extractor.py`
