# InsightXpert Agent Tools Reference

## Overview

InsightXpert has four agents in its pipeline:

| Agent | Mode | Purpose |
|---|---|---|
| **Clarifier** | All modes | Pre-check: decides if the question needs clarification before SQL generation |
| **Analyst** | All modes | Core text-to-SQL loop — queries the DB and produces a natural-language answer |
| **Statistician** | `standard` | Enriches analyst results with statistical analysis |
| **Advanced Agent** | `advanced` | Enriches analyst results with quantitative / domain-specific analytics |

---

## Clarifier

No tools — makes a single lightweight LLM call to detect ambiguous questions.

**Outputs:** `{ "action": "execute" }` or `{ "action": "clarify", "question": "..." }`

---

## Analyst Tools

The analyst uses these three tools in its agentic loop.

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

## Statistician Tools

The statistician runs after the analyst (in `standard` mode) and operates on the analyst's result rows (`df`).

### `run_python`
Execute a Python snippet for custom statistical analysis. Pre-loaded: `np`, `pd`, `stats` (scipy), `math`, `df` (analyst results as DataFrame).

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
| `count_success` | int | z_proportion | Number of successes |
| `count_total` | int | z_proportion | Total trials |
| `hypothesized_proportion` | float | no | H0 proportion for z_proportion (default 0.5) |

**Returns per test:**
- `chi_squared` — statistic, p_value, dof, effect_size_cramers_v, significant_at_005
- `t_test` — statistic, p_value, effect_size_cohens_d, group means & sizes, significant_at_005
- `mann_whitney` — statistic, p_value, effect_size_r, group sizes, significant_at_005
- `anova` — statistic, p_value, effect_size_eta_squared, num_groups, significant_at_005
- `z_proportion` — statistic, p_value, observed_proportion, hypothesized_proportion, sample_size, significant_at_005

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

---

### `run_sql` *(also available to statistician)*
Same as the analyst's `run_sql` — lets the statistician run follow-up queries.

---

## Advanced Agent Tools

The advanced agent runs instead of the statistician when `agent_mode = "advanced"`. It includes all statistician tools (`run_python`, `run_sql`) plus these domain-specific tools:

### Time-Series Tools

#### `compute_time_series_slope`
Fit linear regression (scipy.stats.linregress) to a metric over a time/ordinal index.

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column to analyse |
| `time_column` | string | no | Ordinal/time column for x-axis; uses row index if omitted |

**Returns:** `slope`, `r_squared`, `p_value`, `95% CI`, trend interpretation text

---

#### `compute_area_under_curve`
Compute the area under a time-series curve using `numpy.trapz` — useful for cumulative impact (e.g. total volume over months).

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column (y-values) |
| `time_column` | string | no | Time/ordinal column for non-uniform x-axis |

**Returns:** `auc`, `n_points`, interpretation

---

#### `compute_percentage_change`
Compute period-over-period percentage change in a metric series, plus momentum (accelerating vs. decelerating).

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column |
| `time_column` | string | no | Optional label column for period names |

**Returns:** Array of `{ period, value, pct_change, momentum }`

---

#### `detect_peaks`
Detect local peaks (surge periods) in a numeric series using `scipy.signal.find_peaks`.

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column |
| `time_column` | string | no | Label column for x-axis |
| `top_n` | int | no | Max peaks to return (default 5) |
| `prominence` | float | no | Minimum peak prominence |

**Returns:** Top-N peaks with index, value, surrounding context

---

#### `detect_change_points`
Detect structural change points using variance-minimization (scans all split points, picks minimum within-segment variance), validated with an unpaired t-test.

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column |
| `time_column` | string | no | Label column |
| `n_breakpoints` | int | no | Number of breakpoints to find (default 1) |

**Returns:** Change points with before/after segment stats and t-test p-value

---

### Fraud & Risk Tools

#### `score_fraud_risk`
Compute empirical fraud risk lift for multi-dimensional segments.
Lift = segment_fraud_rate / overall_fraud_rate — high-lift segments are disproportionately fraudulent.

| Arg | Type | Required | Description |
|---|---|---|---|
| `fraud_column` | string | yes | Binary fraud flag column (0/1 or True/False) |
| `segment_columns` | string[] | yes | Categorical columns to segment by |
| `top_n` | int | no | Return top-N highest-risk segments (default 10) |

**Returns:** Segments ranked by lift with fraud_rate, lift, and count

---

#### `detect_amount_anomalies`
Detect anomalous transaction amounts using the Modified Z-score method (Iglewicz & Hoaglin 1993): `M_i = 0.6745*(x_i - median) / MAD`. More robust than mean/std for fat-tailed financial distributions.

| Arg | Type | Required | Description |
|---|---|---|---|
| `amount_column` | string | yes | Numeric amount column |
| `group_column` | string | no | Optional categorical column to group by |
| `threshold` | float | no | Modified Z-score threshold (default 3.5) |

**Returns:** Anomalous rows with modified_z_score, median, MAD per group

---

#### `test_temporal_fraud_clustering`
Test whether fraud is uniformly distributed across time periods (hour_of_day, day_of_week, etc.) using a chi-squared goodness-of-fit test. Shannon entropy measures concentration. Significant result = temporal clustering of fraud.

| Arg | Type | Required | Description |
|---|---|---|---|
| `time_column` | string | yes | Temporal column (e.g. `hour_of_day`) |
| `fraud_column` | string | yes | Binary fraud flag column |

**Returns:** chi2, p_value, entropy, expected vs. observed distribution, significant_at_005

---

#### `compute_bank_pair_risk`
Compute fraud risk for each sender_bank × receiver_bank pair. Z-tests each pair's fraud rate against the overall baseline with Bonferroni correction for multiple comparisons.

| Arg | Type | Required | Description |
|---|---|---|---|
| `sender_column` | string | yes | Sender bank/entity column |
| `receiver_column` | string | yes | Receiver bank/entity column |
| `fraud_column` | string | yes | Binary fraud flag column |
| `top_n` | int | no | Return top-N riskiest pairs (default 10) |

**Returns:** Pairs ranked by fraud_rate with z_score, bonferroni_p, significant flag

---

### General Analytics Tools

#### `compute_percentile_rank`
Rank segments (states, banks, categories) by a numeric metric and assign quartile or decile buckets — useful for benchmarking and performance tiering.

| Arg | Type | Required | Description |
|---|---|---|---|
| `metric_column` | string | yes | Numeric column to rank |
| `segment_column` | string | yes | Categorical column for segments |
| `bins` | enum | no | `quartile` (4 bins, default) or `decile` (10 bins) |
| `ascending` | bool | no | Rank direction (default true) |

**Returns:** Segments with percentile_rank, bucket label, value

---

#### `compute_concentration_index`
Compute the Herfindahl-Hirschman Index (HHI = Σ(share_i²) × 10000).
- 0–1500: competitive
- 1500–2500: moderate concentration
- >2500: highly concentrated

| Arg | Type | Required | Description |
|---|---|---|---|
| `category_column` | string | yes | Categorical column |
| `value_column` | string | no | Numeric weight column; uses row counts if absent |

**Returns:** `hhi`, `interpretation`, top contributors with share

---

#### `test_benford_law`
Test whether transaction amounts conform to Benford's law (expected first-digit distribution: `P(d) = log10(1 + 1/d)`). Significant deviation may indicate data quality issues or synthetic generation artifacts. Requires ≥ 100 data points.

| Arg | Type | Required | Description |
|---|---|---|---|
| `amount_column` | string | yes | Numeric amount column |

**Returns:** chi2, p_value, observed vs. expected first-digit frequencies, significant_at_005
