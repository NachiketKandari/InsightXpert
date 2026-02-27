"""Advanced analytics tools for the advanced agent.

Provides three categories of tools:
- Time-series: slope, AUC, % change, peaks, change-points
- Fraud & risk: fraud scoring, anomaly detection, temporal clustering, bank-pair risk
- General: percentile ranking, concentration index (HHI), Benford's law
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import signal, stats

from insightxpert.agents.stat_tools import RunPythonTool
from insightxpert.agents.tool_base import Tool, ToolContext, ToolRegistry
from insightxpert.agents.tools import RunSqlTool

__all__ = [
    # Time-series
    "ComputeTimeSeriesSlopeTool",
    "ComputeAreaUnderCurveTool",
    "ComputePercentageChangeTool",
    "DetectPeaksTool",
    "DetectChangePointsTool",
    # Fraud & risk
    "ScoreFraudRiskTool",
    "DetectAmountAnomaliesTool",
    "TestTemporalFraudClusteringTool",
    "ComputeBankPairRiskTool",
    # General
    "ComputePercentileRankTool",
    "ComputeConcentrationIndexTool",
    "TestBenfordLawTool",
    # Factory
    "advanced_registry",
]

logger = logging.getLogger("insightxpert.advanced_tools")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _df(context: ToolContext) -> pd.DataFrame:
    """Convert analyst_results to DataFrame; returns empty DF if none."""
    if not context.analyst_results:
        return pd.DataFrame()
    return pd.DataFrame(context.analyst_results)


def _require_columns(df: pd.DataFrame, *cols: str) -> str | None:
    """Return JSON error string if any col is missing, else None."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        available = list(df.columns)
        return json.dumps({"error": f"Column(s) {missing} not found. Available: {available}"})
    return None


# ===========================================================================
# Section A — Time-Series Tools
# ===========================================================================

class ComputeTimeSeriesSlopeTool(Tool):
    """Fit linear regression to a numeric metric over an ordinal/temporal index."""

    @property
    def name(self) -> str:
        return "compute_time_series_slope"

    @property
    def description(self) -> str:
        return (
            "Fit linear regression (scipy.stats.linregress) to a numeric metric over a "
            "time or ordinal index. Returns slope, R², p-value, 95% CI, and a plain-text "
            "interpretation of the trend direction and strength. Requires at least 2 rows."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value_column": {
                    "type": "string",
                    "description": "Numeric column to fit regression on (y-axis).",
                },
                "time_column": {
                    "type": "string",
                    "description": (
                        "Optional column to use as x-axis. If absent, row order (0, 1, 2...) "
                        "is used as the ordinal index."
                    ),
                },
                "time_unit": {
                    "type": "string",
                    "enum": ["day", "week", "month"],
                    "description": "Label for the time unit (for interpretation text only).",
                },
            },
            "required": ["value_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        val_col: str = args["value_column"]
        time_col: str | None = args.get("time_column")
        time_unit: str = args.get("time_unit", "period")

        err = _require_columns(df, val_col)
        if err:
            return err
        if time_col and time_col not in df.columns:
            return json.dumps({"error": f"time_column '{time_col}' not found. Available: {list(df.columns)}"})

        y = pd.to_numeric(df[val_col], errors="coerce")
        if time_col:
            x_raw = pd.to_numeric(df[time_col], errors="coerce")
            valid = y.notna() & x_raw.notna()
            x = x_raw[valid].values.astype(float)
            y = y[valid].values.astype(float)
        else:
            valid = y.notna()
            y = y[valid].values.astype(float)
            x = np.arange(len(y), dtype=float)

        if len(y) < 2:
            return json.dumps({"error": f"Need at least 2 data points (got {len(y)})"})

        # All-same values → flat line
        if np.std(y) == 0:
            return json.dumps({
                "slope": 0.0,
                "intercept": round(float(y[0]), 6),
                "r_squared": 0.0,
                "p_value": 1.0,
                "std_error": 0.0,
                "ci_95": [0.0, 0.0],
                "trend_direction": "flat",
                "interpretation": f"The {val_col} is constant across all {time_unit}s; no trend detected.",
            })

        try:
            result = stats.linregress(x, y)
        except Exception as exc:
            logger.error("linregress failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})

        slope = float(result.slope)
        intercept = float(result.intercept)
        r_sq = float(result.rvalue ** 2)
        p_val = float(result.pvalue)
        stderr = float(result.stderr)

        # 95% CI on slope: slope ± t_{n-2, 0.975} * stderr
        n = len(y)
        t_crit = float(stats.t.ppf(0.975, df=n - 2)) if n > 2 else 1.96
        ci = [round(slope - t_crit * stderr, 6), round(slope + t_crit * stderr, 6)]

        direction = "increasing" if slope > 0 else ("decreasing" if slope < 0 else "flat")
        strength = "strongly" if r_sq >= 0.7 else ("moderately" if r_sq >= 0.4 else "weakly")
        sig = "statistically significant" if p_val < 0.05 else "not statistically significant"
        interpretation = (
            f"{val_col} is {strength} {direction} at {abs(slope):.4f} units per {time_unit} "
            f"(R²={r_sq:.4f}, p={p_val:.4f}); trend is {sig}."
        )

        return json.dumps({
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "r_squared": round(r_sq, 6),
            "p_value": round(p_val, 6),
            "std_error": round(stderr, 6),
            "ci_95": ci,
            "trend_direction": direction,
            "interpretation": interpretation,
        })


class ComputeAreaUnderCurveTool(Tool):
    """Compute AUC via numpy.trapz to quantify cumulative impact over time."""

    @property
    def name(self) -> str:
        return "compute_area_under_curve"

    @property
    def description(self) -> str:
        return (
            "Compute the area under a time-series curve using numpy.trapz. "
            "Useful for quantifying cumulative impact (e.g. total transaction volume over months). "
            "If a time_column is provided it is used as the non-uniform x-axis."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value_column": {
                    "type": "string",
                    "description": "Numeric column to integrate (y-values).",
                },
                "time_column": {
                    "type": "string",
                    "description": "Optional numeric time column for non-uniform spacing (x-values).",
                },
            },
            "required": ["value_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        val_col: str = args["value_column"]
        time_col: str | None = args.get("time_column")

        err = _require_columns(df, val_col)
        if err:
            return err

        y = pd.to_numeric(df[val_col], errors="coerce")

        if time_col:
            if time_col not in df.columns:
                return json.dumps({"error": f"time_column '{time_col}' not found. Available: {list(df.columns)}"})
            x_raw = pd.to_numeric(df[time_col], errors="coerce")
            valid = y.notna() & x_raw.notna()
            x = x_raw[valid].values.astype(float)
            y_arr = y[valid].values.astype(float)
        else:
            valid = y.notna()
            y_arr = y[valid].values.astype(float)
            x = None

        n = len(y_arr)
        if n < 2:
            return json.dumps({"error": f"Need at least 2 data points (got {n})"})

        try:
            auc = float(np.trapz(y_arr, x=x))
        except Exception as exc:
            logger.error("trapz failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})

        interpretation = (
            f"The cumulative area under {val_col} is {auc:.4f}. "
            f"Mean value per period: {float(np.mean(y_arr)):.4f}."
        )

        return json.dumps({
            "auc": round(auc, 6),
            "n_points": n,
            "sum": round(float(np.sum(y_arr)), 6),
            "mean": round(float(np.mean(y_arr)), 6),
            "interpretation": interpretation,
        })


class ComputePercentageChangeTool(Tool):
    """Compute period-over-period % change and momentum direction."""

    @property
    def name(self) -> str:
        return "compute_percentage_change"

    @property
    def description(self) -> str:
        return (
            "Compute period-over-period percentage change in a metric series. "
            "Also computes momentum (sign of the 2nd derivative: accelerating vs. decelerating). "
            "Requires at least 2 data points."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value_column": {
                    "type": "string",
                    "description": "Numeric column to compute changes on.",
                },
                "time_column": {
                    "type": "string",
                    "description": "Optional column used only for row ordering (values not used numerically).",
                },
                "lag": {
                    "type": "integer",
                    "description": "Number of periods to lag for the comparison (default 1).",
                },
            },
            "required": ["value_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        val_col: str = args["value_column"]
        lag: int = int(args.get("lag", 1))

        err = _require_columns(df, val_col)
        if err:
            return err

        series = pd.to_numeric(df[val_col], errors="coerce").dropna().reset_index(drop=True)
        if len(series) < 2:
            return json.dumps({"error": f"Need at least 2 data points (got {len(series)})"})

        pct_changes = series.pct_change(periods=lag).dropna() * 100
        if pct_changes.empty:
            return json.dumps({"error": "Could not compute percentage changes (too few rows or lag too large)"})

        # Momentum: sign of mean 2nd derivative (diff of pct_changes)
        second_deriv = pct_changes.diff().dropna()
        if len(second_deriv) > 0:
            mean_accel = float(second_deriv.mean())
            momentum = "accelerating" if mean_accel > 0 else ("decelerating" if mean_accel < 0 else "steady")
        else:
            momentum = "steady"

        pos = int((pct_changes > 0).sum())
        neg = int((pct_changes < 0).sum())

        return json.dumps({
            "n_periods": len(pct_changes),
            "lag": lag,
            "mean_pct_change": round(float(pct_changes.mean()), 4),
            "std_pct_change": round(float(pct_changes.std()), 4),
            "min_pct_change": round(float(pct_changes.min()), 4),
            "max_pct_change": round(float(pct_changes.max()), 4),
            "periods_positive": pos,
            "periods_negative": neg,
            "momentum_direction": momentum,
            "interpretation": (
                f"{val_col} changed by {float(pct_changes.mean()):.2f}% per period on average "
                f"({pos} periods up, {neg} down). Momentum: {momentum}."
            ),
        })


class DetectPeaksTool(Tool):
    """Identify surge periods in a metric using scipy.signal.find_peaks."""

    @property
    def name(self) -> str:
        return "detect_peaks"

    @property
    def description(self) -> str:
        return (
            "Detect local peaks (surge periods) in a numeric series using scipy.signal.find_peaks. "
            "Returns the top-N peaks with their surrounding context. "
            "Requires at least 3 data points."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value_column": {
                    "type": "string",
                    "description": "Numeric column to search for peaks.",
                },
                "time_column": {
                    "type": "string",
                    "description": "Optional column used to label peaks (e.g. month, date).",
                },
                "num_peaks": {
                    "type": "integer",
                    "description": "Maximum number of top peaks to return (default 5).",
                },
                "min_prominence_ratio": {
                    "type": "number",
                    "description": (
                        "Minimum prominence as fraction of value range (0-1, default 0.2). "
                        "Higher values filter out minor bumps."
                    ),
                },
            },
            "required": ["value_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        val_col: str = args["value_column"]
        time_col: str | None = args.get("time_column")
        num_peaks: int = int(args.get("num_peaks", 5))
        prom_ratio: float = float(args.get("min_prominence_ratio", 0.2))

        err = _require_columns(df, val_col)
        if err:
            return err

        y = pd.to_numeric(df[val_col], errors="coerce")
        valid_mask = y.notna()
        y_clean = y[valid_mask].values.astype(float)

        if len(y_clean) < 3:
            return json.dumps({"error": f"Need at least 3 data points (got {len(y_clean)})"})

        val_range = float(np.ptp(y_clean))
        prominence = prom_ratio * val_range if val_range > 0 else 0.0

        try:
            peak_indices, properties = signal.find_peaks(y_clean, prominence=prominence)
        except Exception as exc:
            logger.error("find_peaks failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})

        if len(peak_indices) == 0:
            return json.dumps({
                "n_peaks_found": 0,
                "top_peaks": [],
                "interpretation": f"No peaks found in {val_col} at prominence threshold {prom_ratio:.2f}.",
            })

        # Sort by value descending, take top-N
        sorted_idx = peak_indices[np.argsort(y_clean[peak_indices])[::-1]][:num_peaks]

        # Map back to original df indices
        original_indices = df[valid_mask].index.tolist()
        surrounding_window = max(1, len(y_clean) // 10)
        overall_avg = float(np.mean(y_clean))

        top_peaks: list[dict[str, Any]] = []
        for i in sorted(sorted_idx):  # sort by position for readability
            orig_idx = original_indices[i]
            val = float(y_clean[i])
            # Surrounding average (exclude the peak itself)
            surr_slice = np.concatenate([
                y_clean[max(0, i - surrounding_window):i],
                y_clean[i + 1:min(len(y_clean), i + surrounding_window + 1)],
            ])
            surr_avg = float(np.mean(surr_slice)) if len(surr_slice) > 0 else overall_avg
            dev_pct = ((val - surr_avg) / surr_avg * 100) if surr_avg != 0 else 0.0

            label: Any = None
            if time_col and time_col in df.columns:
                label = df.loc[orig_idx, time_col]

            top_peaks.append({
                "index": int(orig_idx),
                "label": str(label) if label is not None else int(orig_idx),
                "value": round(val, 4),
                "surrounding_avg": round(surr_avg, 4),
                "deviation_from_avg_pct": round(dev_pct, 2),
            })

        return json.dumps({
            "n_peaks_found": len(peak_indices),
            "top_peaks": top_peaks,
            "interpretation": (
                f"Found {len(peak_indices)} peak(s) in {val_col}. "
                f"Top peak value: {top_peaks[0]['value']:.4f} "
                f"({top_peaks[0]['deviation_from_avg_pct']:+.1f}% above surroundings)."
            ),
        })


class DetectChangePointsTool(Tool):
    """CUSUM-based change point detection using pure numpy/scipy."""

    @property
    def name(self) -> str:
        return "detect_change_points"

    @property
    def description(self) -> str:
        return (
            "Detect structural change points in a numeric series using variance-minimization "
            "(scans all valid split points, picks the one minimising total within-segment variance) "
            "followed by an unpaired t-test for significance. "
            "No external dependencies beyond numpy and scipy. "
            f"Requires at least 2*min_segment_size rows."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value_column": {
                    "type": "string",
                    "description": "Numeric column to scan for change points.",
                },
                "time_column": {
                    "type": "string",
                    "description": "Optional column used to label change-point positions.",
                },
                "min_segment_size": {
                    "type": "integer",
                    "description": "Minimum number of rows in each segment (default 5).",
                },
            },
            "required": ["value_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        val_col: str = args["value_column"]
        time_col: str | None = args.get("time_column")
        min_seg: int = int(args.get("min_segment_size", 5))

        err = _require_columns(df, val_col)
        if err:
            return err

        y = pd.to_numeric(df[val_col], errors="coerce")
        valid_mask = y.notna()
        y_arr = y[valid_mask].values.astype(float)
        original_indices = df[valid_mask].index.tolist()
        n = len(y_arr)

        if n < 2 * min_seg:
            return json.dumps({
                "error": (
                    f"Need at least {2 * min_seg} data points for change point detection "
                    f"with min_segment_size={min_seg} (got {n})"
                )
            })

        # Scan all candidate split points and find the one minimising total within-segment SSE
        best_split: int = -1
        best_sse: float = float("inf")

        for i in range(min_seg, n - min_seg + 1):
            seg1 = y_arr[:i]
            seg2 = y_arr[i:]
            sse = float(np.sum((seg1 - seg1.mean()) ** 2) + np.sum((seg2 - seg2.mean()) ** 2))
            if sse < best_sse:
                best_sse = sse
                best_split = i

        if best_split < 0:
            return json.dumps({"n_changepoints": 0, "changepoints": [],
                               "interpretation": "No valid split point found."})

        seg1 = y_arr[:best_split]
        seg2 = y_arr[best_split:]
        mean_before = float(seg1.mean())
        mean_after = float(seg2.mean())
        pct_change = ((mean_after - mean_before) / abs(mean_before) * 100) if mean_before != 0 else 0.0

        try:
            t_stat, p_value = stats.ttest_ind(seg1, seg2, equal_var=False)
        except Exception as exc:
            logger.error("ttest_ind failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})

        significant = bool(float(p_value) < 0.05)

        orig_idx = original_indices[best_split]
        label: Any = None
        if time_col and time_col in df.columns:
            label = df.loc[orig_idx, time_col]

        cp = {
            "index": int(orig_idx),
            "label": str(label) if label is not None else int(orig_idx),
            "mean_before": round(mean_before, 4),
            "mean_after": round(mean_after, 4),
            "pct_change": round(pct_change, 2),
            "t_stat": round(float(t_stat), 4),
            "p_value": round(float(p_value), 6),
            "significant": significant,
        }

        direction = "increased" if mean_after > mean_before else "decreased"
        sig_text = "significant" if significant else "not statistically significant"
        interpretation = (
            f"Best change point at position {cp['label']}: {val_col} {direction} by "
            f"{abs(pct_change):.1f}% (from {mean_before:.4f} to {mean_after:.4f}); "
            f"t-test p={float(p_value):.4f} — {sig_text}."
        )

        return json.dumps({
            "n_changepoints": 1 if significant else 0,
            "changepoints": [cp],
            "interpretation": interpretation,
        })


# ===========================================================================
# Section B — Fraud & Risk Tools
# ===========================================================================

class ScoreFraudRiskTool(Tool):
    """Compute empirical lift = segment_fraud_rate / overall_fraud_rate for multi-dim groups."""

    @property
    def name(self) -> str:
        return "score_fraud_risk"

    @property
    def description(self) -> str:
        return (
            "Compute empirical fraud risk lift for multi-dimensional segments. "
            "Lift = segment_fraud_rate / overall_fraud_rate. "
            "High-lift segments are disproportionately fraudulent. "
            "Requires a binary fraud flag column (0/1 or True/False)."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "group_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of categorical columns to group by (e.g. ['payment_method', 'state']).",
                },
                "fraud_column": {
                    "type": "string",
                    "description": "Binary fraud flag column (0/1 or True/False). Default: 'fraud_flag'.",
                },
                "min_segment_size": {
                    "type": "integer",
                    "description": "Minimum rows in a segment to include (default 10).",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of highest-lift segments to return (default 10).",
                },
            },
            "required": ["group_columns"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        group_cols: list[str] = args["group_columns"]
        fraud_col: str = args.get("fraud_column", "fraud_flag")
        min_size: int = int(args.get("min_segment_size", 10))
        top_n: int = int(args.get("top_n", 10))

        all_cols = group_cols + [fraud_col]
        err = _require_columns(df, *all_cols)
        if err:
            return err

        fraud_series = pd.to_numeric(df[fraud_col], errors="coerce").fillna(0)
        overall_rate = float(fraud_series.mean())

        if overall_rate == 0:
            return json.dumps({"error": "No fraud cases found in the data (overall_fraud_rate = 0)"})

        grouped = df.groupby(group_cols)[fraud_col].agg(
            segment_size="count",
            fraud_count=lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum(),
        ).reset_index()

        grouped = grouped[grouped["segment_size"] >= min_size].copy()
        if grouped.empty:
            return json.dumps({"error": f"No segments with at least {min_size} rows found"})

        grouped["fraud_rate"] = grouped["fraud_count"] / grouped["segment_size"]
        grouped["lift"] = grouped["fraud_rate"] / overall_rate

        # Chi-squared contribution per segment: (O - E)^2 / E
        grouped["expected_fraud"] = grouped["segment_size"] * overall_rate
        grouped["chi2_contribution"] = (
            (grouped["fraud_count"] - grouped["expected_fraud"]) ** 2
        ) / grouped["expected_fraud"].clip(lower=1e-9)

        top = grouped.nlargest(top_n, "lift")

        segments: list[dict[str, Any]] = []
        for _, row in top.iterrows():
            seg: dict[str, Any] = {col: str(row[col]) for col in group_cols}
            seg.update({
                "segment_size": int(row["segment_size"]),
                "fraud_rate": round(float(row["fraud_rate"]), 6),
                "lift": round(float(row["lift"]), 4),
                "chi2_contribution": round(float(row["chi2_contribution"]), 4),
            })
            segments.append(seg)

        return json.dumps({
            "overall_fraud_rate": round(overall_rate, 6),
            "high_risk_segments": segments,
            "interpretation": (
                f"Overall fraud rate: {overall_rate:.4%}. "
                f"Top segment lift: {segments[0]['lift']:.2f}× "
                f"({segments[0]['fraud_rate']:.4%} fraud rate)."
                if segments else "No high-risk segments found."
            ),
        })


class DetectAmountAnomaliesTool(Tool):
    """Modified Z-score (MAD-based) anomaly detection for transaction amounts."""

    @property
    def name(self) -> str:
        return "detect_amount_anomalies"

    @property
    def description(self) -> str:
        return (
            "Detect anomalous transaction amounts using the Modified Z-score method "
            "(Iglewicz & Hoaglin 1993): M_i = 0.6745*(x_i - median) / MAD. "
            "More robust than mean/std for fat-tailed financial distributions. "
            "Can optionally group by a categorical column."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "amount_column": {
                    "type": "string",
                    "description": "Numeric amount column. Default: 'amount_inr'.",
                },
                "group_by": {
                    "type": "string",
                    "description": "Optional categorical column to compute anomalies per group.",
                },
                "z_threshold": {
                    "type": "number",
                    "description": "Modified Z-score threshold for anomaly flag (default 3.5).",
                },
            },
        }

    def _mad_z_scores(self, series: pd.Series) -> pd.Series:
        """Compute modified Z-scores: M_i = 0.6745 * (x_i - median) / MAD."""
        median = series.median()
        mad = (series - median).abs().median()
        if mad == 0:
            return pd.Series(np.zeros(len(series)), index=series.index)
        return 0.6745 * (series - median) / mad

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        amount_col: str = args.get("amount_column", "amount_inr")
        group_col: str | None = args.get("group_by")
        z_thresh: float = float(args.get("z_threshold", 3.5))

        err = _require_columns(df, amount_col)
        if err:
            return err
        if group_col and group_col not in df.columns:
            return json.dumps({"error": f"group_by column '{group_col}' not found. Available: {list(df.columns)}"})

        amounts = pd.to_numeric(df[amount_col], errors="coerce")
        df_clean = df.copy()
        df_clean["_amount"] = amounts
        df_clean = df_clean[df_clean["_amount"].notna()]

        if df_clean.empty:
            return json.dumps({"error": f"No valid numeric values in '{amount_col}'"})

        def _group_stats(sub: pd.DataFrame) -> dict[str, Any]:
            s = sub["_amount"]
            z_scores = self._mad_z_scores(s)
            anomaly_mask = z_scores.abs() > z_thresh
            anomalies = s[anomaly_mask]
            return {
                "group_size": len(s),
                "anomaly_count": int(anomaly_mask.sum()),
                "anomaly_rate": round(float(anomaly_mask.mean()), 6),
                "median": round(float(s.median()), 4),
                "mad": round(float((s - s.median()).abs().median()), 4),
                "min_anomaly_amount": round(float(anomalies.min()), 4) if not anomalies.empty else None,
                "max_anomaly_amount": round(float(anomalies.max()), 4) if not anomalies.empty else None,
            }

        if group_col:
            results_by_group: list[dict[str, Any]] = []
            for group_val, sub in df_clean.groupby(group_col):
                entry = {"group": str(group_val)}
                entry.update(_group_stats(sub))
                results_by_group.append(entry)

            total_anomalies = sum(g["anomaly_count"] for g in results_by_group)
            return json.dumps({
                "method": "modified_z_score",
                "z_threshold": z_thresh,
                "results_by_group": results_by_group,
                "interpretation": (
                    f"Detected {total_anomalies} anomalous {amount_col} values across "
                    f"{len(results_by_group)} groups using MAD-based Z-score (threshold {z_thresh})."
                ),
            })
        else:
            stats_dict = _group_stats(df_clean)
            return json.dumps({
                "method": "modified_z_score",
                "z_threshold": z_thresh,
                **stats_dict,
                "interpretation": (
                    f"Detected {stats_dict['anomaly_count']} anomalous {amount_col} values "
                    f"({stats_dict['anomaly_rate']:.2%} of {stats_dict['group_size']}) "
                    f"using MAD-based Z-score (threshold {z_thresh})."
                ),
            })


class TestTemporalFraudClusteringTool(Tool):
    """Chi-squared GoF test for temporal concentration of fraud."""

    @property
    def name(self) -> str:
        return "test_temporal_fraud_clustering"

    @property
    def description(self) -> str:
        return (
            "Test whether fraud is uniformly distributed across time periods (e.g. hour_of_day, day_of_week) "
            "using a chi-squared goodness-of-fit test. Shannon entropy measures concentration. "
            "A significant result indicates temporal clustering of fraud."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "time_column": {
                    "type": "string",
                    "description": "Categorical/ordinal time column (e.g. 'hour_of_day'). Default: 'hour_of_day'.",
                },
                "fraud_column": {
                    "type": "string",
                    "description": "Binary fraud flag column (0/1). Default: 'fraud_flag'.",
                },
                "alpha": {
                    "type": "number",
                    "description": "Significance level (default 0.05).",
                },
            },
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        time_col: str = args.get("time_column", "hour_of_day")
        fraud_col: str = args.get("fraud_column", "fraud_flag")
        alpha: float = float(args.get("alpha", 0.05))

        err = _require_columns(df, time_col, fraud_col)
        if err:
            return err

        fraud_series = pd.to_numeric(df[fraud_col], errors="coerce").fillna(0)
        fraud_mask = fraud_series == 1

        if not fraud_mask.any():
            return json.dumps({"error": "No fraud cases found in the data"})

        fraud_by_period = df[fraud_mask][time_col].value_counts().sort_index()
        total_fraud = int(fraud_mask.sum())

        observed = fraud_by_period.values.astype(float)
        n_periods = len(observed)
        expected = np.full(n_periods, total_fraud / n_periods)

        try:
            chi2_stat, p_value = stats.chisquare(observed, f_exp=expected)
        except Exception as exc:
            logger.error("chisquare failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})

        # Shannon entropy
        probs = observed / observed.sum()
        entropy = float(-np.sum(probs * np.log2(probs + 1e-12)))
        max_entropy = float(np.log2(n_periods)) if n_periods > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        peak_periods = []
        for period, count in zip(fraud_by_period.index, fraud_by_period.values):
            peak_periods.append({
                "period": str(period),
                "fraud_count": int(count),
                "pct_of_fraud": round(float(count) / total_fraud * 100, 2),
            })
        peak_periods.sort(key=lambda x: x["fraud_count"], reverse=True)

        significant = bool(float(p_value) < alpha)
        sig_text = "significantly clustered" if significant else "uniformly distributed"

        return json.dumps({
            "total_fraud_cases": total_fraud,
            "n_periods": n_periods,
            "chi2_stat": round(float(chi2_stat), 4),
            "p_value": round(float(p_value), 6),
            "significant": significant,
            "entropy": round(entropy, 4),
            "normalized_entropy": round(normalized_entropy, 4),
            "peak_periods": peak_periods[:5],
            "interpretation": (
                f"Fraud is {sig_text} across {n_periods} {time_col} periods "
                f"(χ²={chi2_stat:.2f}, p={p_value:.4f}). "
                f"Normalized entropy: {normalized_entropy:.3f} "
                f"(0=maximally concentrated, 1=uniform)."
            ),
        })


class ComputeBankPairRiskTool(Tool):
    """Sender×receiver fraud rate matrix with z-test and Bonferroni correction."""

    @property
    def name(self) -> str:
        return "compute_bank_pair_risk"

    @property
    def description(self) -> str:
        return (
            "Compute fraud risk for each sender_bank × receiver_bank pair. "
            "Z-tests each pair's fraud rate against the overall baseline, "
            "with Bonferroni correction for multiple comparisons. "
            "Returns the highest-risk pairs."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sender_col": {
                    "type": "string",
                    "description": "Sender bank column. Default: 'sender_bank'.",
                },
                "receiver_col": {
                    "type": "string",
                    "description": "Receiver bank column. Default: 'receiver_bank'.",
                },
                "fraud_col": {
                    "type": "string",
                    "description": "Binary fraud flag column. Default: 'fraud_flag'.",
                },
                "min_pair_size": {
                    "type": "integer",
                    "description": "Minimum transactions for a pair to be included (default 5).",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of riskiest pairs to return (default 5).",
                },
            },
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        sender_col: str = args.get("sender_col", "sender_bank")
        receiver_col: str = args.get("receiver_col", "receiver_bank")
        fraud_col: str = args.get("fraud_col", "fraud_flag")
        min_size: int = int(args.get("min_pair_size", 5))
        top_n: int = int(args.get("top_n", 5))

        err = _require_columns(df, sender_col, receiver_col, fraud_col)
        if err:
            return err

        fraud_series = pd.to_numeric(df[fraud_col], errors="coerce").fillna(0)
        baseline = float(fraud_series.mean())

        if baseline == 0:
            return json.dumps({"error": "No fraud cases found (baseline_fraud_rate = 0)"})

        grouped = df.groupby([sender_col, receiver_col])[fraud_col].agg(
            pair_size="count",
            fraud_count=lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum(),
        ).reset_index()

        grouped = grouped[grouped["pair_size"] >= min_size].copy()
        if grouped.empty:
            return json.dumps({"error": f"No pairs with at least {min_size} transactions"})

        n_pairs = len(grouped)
        bonferroni_alpha = 0.05 / n_pairs

        grouped["fraud_rate"] = grouped["fraud_count"] / grouped["pair_size"]
        grouped["lift"] = grouped["fraud_rate"] / baseline

        # Z-test: (p_hat - p0) / sqrt(p0*(1-p0)/n)
        se = np.sqrt(baseline * (1 - baseline) / grouped["pair_size"])
        grouped["z_score"] = (grouped["fraud_rate"] - baseline) / se.clip(lower=1e-9)
        grouped["p_value"] = 2 * (1 - stats.norm.cdf(grouped["z_score"].abs()))
        grouped["significant_after_bonferroni"] = grouped["p_value"] < bonferroni_alpha

        top = grouped.nlargest(top_n, "fraud_rate")

        pairs: list[dict[str, Any]] = []
        for _, row in top.iterrows():
            pairs.append({
                "sender": str(row[sender_col]),
                "receiver": str(row[receiver_col]),
                "pair_size": int(row["pair_size"]),
                "fraud_rate": round(float(row["fraud_rate"]), 6),
                "lift": round(float(row["lift"]), 4),
                "z_score": round(float(row["z_score"]), 4),
                "p_value": round(float(row["p_value"]), 6),
                "significant_after_bonferroni": bool(row["significant_after_bonferroni"]),
            })

        return json.dumps({
            "baseline_fraud_rate": round(baseline, 6),
            "n_pairs_evaluated": n_pairs,
            "bonferroni_threshold": round(bonferroni_alpha, 8),
            "top_riskiest_pairs": pairs,
            "interpretation": (
                f"Baseline fraud rate: {baseline:.4%}. "
                f"Riskiest pair: {pairs[0]['sender']} → {pairs[0]['receiver']} "
                f"({pairs[0]['fraud_rate']:.4%} fraud rate, {pairs[0]['lift']:.2f}× lift). "
                f"Bonferroni threshold: p < {bonferroni_alpha:.6f}."
                if pairs else "No risky bank pairs found."
            ),
        })


# ===========================================================================
# Section C — General Advanced Tools
# ===========================================================================

class ComputePercentileRankTool(Tool):
    """Rank segments by a metric and assign quartile/decile buckets."""

    @property
    def name(self) -> str:
        return "compute_percentile_rank"

    @property
    def description(self) -> str:
        return (
            "Rank segments (states, banks, categories) by a numeric metric and assign "
            "quartile (4-bin) or decile (10-bin) buckets. "
            "Useful for benchmarking and performance tiering."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "metric_column": {
                    "type": "string",
                    "description": "Numeric column to rank by.",
                },
                "group_column": {
                    "type": "string",
                    "description": "Categorical column identifying each segment.",
                },
                "n_bins": {
                    "type": "integer",
                    "enum": [4, 10],
                    "description": "Number of bins: 4 (quartile) or 10 (decile). Default: 4.",
                },
            },
            "required": ["metric_column", "group_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        metric_col: str = args["metric_column"]
        group_col: str = args["group_column"]
        n_bins: int = int(args.get("n_bins", 4))

        err = _require_columns(df, metric_col, group_col)
        if err:
            return err

        agg = df.groupby(group_col)[metric_col].agg(
            lambda x: pd.to_numeric(x, errors="coerce").mean()
        ).dropna().reset_index()
        agg.columns = [group_col, metric_col]

        if agg.empty:
            return json.dumps({"error": "No valid numeric values after grouping"})

        agg = agg.sort_values(metric_col, ascending=False).reset_index(drop=True)
        n = len(agg)
        agg["rank"] = agg[metric_col].rank(ascending=False, method="min").astype(int)
        agg["percentile"] = ((n - agg["rank"]) / max(n - 1, 1) * 100).round(1)

        bin_labels_4 = ["Q1 (bottom 25%)", "Q2 (25-50%)", "Q3 (50-75%)", "Q4 (top 25%)"]
        bin_labels_10 = [f"D{i}" for i in range(1, 11)]

        if n_bins == 10:
            labels = bin_labels_10
        else:
            labels = bin_labels_4

        try:
            agg["bucket_label"] = pd.qcut(
                agg[metric_col], q=n_bins, labels=labels, duplicates="drop",
            ).astype(str)
        except ValueError:
            agg["bucket_label"] = "N/A"

        ranked_segments: list[dict[str, Any]] = []
        for _, row in agg.iterrows():
            ranked_segments.append({
                "group": str(row[group_col]),
                "value": round(float(row[metric_col]), 4),
                "rank": int(row["rank"]),
                "percentile": float(row["percentile"]),
                "bucket_label": str(row["bucket_label"]),
            })

        return json.dumps({
            "metric": metric_col,
            "group_column": group_col,
            "n_bins": n_bins,
            "ranked_segments": ranked_segments,
            "interpretation": (
                f"Ranked {n} {group_col} segments by {metric_col}. "
                f"Top: {ranked_segments[0]['group']} ({ranked_segments[0]['value']:.4f}). "
                f"Bottom: {ranked_segments[-1]['group']} ({ranked_segments[-1]['value']:.4f})."
            ),
        })


class ComputeConcentrationIndexTool(Tool):
    """Compute Herfindahl-Hirschman Index (HHI) for market/segment concentration."""

    @property
    def name(self) -> str:
        return "compute_concentration_index"

    @property
    def description(self) -> str:
        return (
            "Compute the Herfindahl-Hirschman Index (HHI = Σ(share_i²) × 10000) for a categorical column. "
            "Interpretation: 0-1500 = competitive, 1500-2500 = moderate, >2500 = concentrated. "
            "If value_column is absent, counts rows per group."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "group_column": {
                    "type": "string",
                    "description": "Categorical column defining segments.",
                },
                "value_column": {
                    "type": "string",
                    "description": "Optional numeric column to sum per group (defaults to row counts).",
                },
            },
            "required": ["group_column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        group_col: str = args["group_column"]
        value_col: str | None = args.get("value_column")

        err = _require_columns(df, group_col)
        if err:
            return err

        if value_col:
            if value_col not in df.columns:
                return json.dumps({"error": f"value_column '{value_col}' not found. Available: {list(df.columns)}"})
            agg = pd.to_numeric(df[value_col], errors="coerce").fillna(0).groupby(df[group_col]).sum()
        else:
            agg = df[group_col].value_counts()

        agg = agg[agg > 0]
        if agg.empty:
            return json.dumps({"error": "No positive values found for HHI computation"})

        total = float(agg.sum())
        shares = agg / total
        hhi = float((shares ** 2).sum() * 10000)

        if hhi < 1500:
            interpretation_label = "competitive"
        elif hhi < 2500:
            interpretation_label = "moderately concentrated"
        else:
            interpretation_label = "highly concentrated"

        top3_share = float(shares.nlargest(3).sum() * 100)

        segments: list[dict[str, Any]] = []
        for group, val in agg.sort_values(ascending=False).items():
            segments.append({
                "group": str(group),
                "value": round(float(val), 4),
                "share_pct": round(float(val / total * 100), 4),
            })

        return json.dumps({
            "hhi": round(hhi, 2),
            "interpretation": (
                f"HHI = {hhi:.0f} — {interpretation_label}. "
                f"Top-3 segments hold {top3_share:.1f}% of total."
            ),
            "top_3_share_pct": round(top3_share, 2),
            "n_segments": len(segments),
            "segments": segments,
        })


class TestBenfordLawTool(Tool):
    """Chi-squared test of first-digit distribution against Benford's law."""

    @property
    def name(self) -> str:
        return "test_benford_law"

    @property
    def description(self) -> str:
        return (
            "Test whether transaction amounts conform to Benford's law "
            "(expected first-digit distribution: P(d) = log10(1 + 1/d)). "
            "Significant deviation may indicate data quality issues or synthetic generation artifacts. "
            "Requires at least 100 data points."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "amount_column": {
                    "type": "string",
                    "description": "Numeric amount column. Default: 'amount_inr'.",
                },
            },
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _df(context)
        amount_col: str = args.get("amount_column", "amount_inr")

        err = _require_columns(df, amount_col)
        if err:
            return err

        amounts = pd.to_numeric(df[amount_col], errors="coerce")
        valid = amounts[amounts > 0].dropna()

        if len(valid) < 100:
            return json.dumps({"error": f"Need at least 100 positive values for Benford test (got {len(valid)})"})

        first_digits = valid.apply(lambda x: int(str(x).lstrip("0").lstrip(".")[0]) if str(x).replace(".", "").lstrip("0") else 0)
        first_digits = first_digits[first_digits.between(1, 9)]
        n_valid = len(first_digits)

        # Benford expected frequencies
        benford_expected = {d: np.log10(1 + 1 / d) for d in range(1, 10)}
        observed_counts = first_digits.value_counts().reindex(range(1, 10), fill_value=0)

        expected_counts = np.array([benford_expected[d] * n_valid for d in range(1, 10)])
        observed_arr = observed_counts.values.astype(float)

        try:
            chi2_stat, p_value = stats.chisquare(observed_arr, f_exp=expected_counts)
        except Exception as exc:
            logger.error("Benford chisquare failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc)})

        significant = bool(float(p_value) < 0.05)

        digit_distribution: list[dict[str, Any]] = []
        for d in range(1, 10):
            obs_pct = float(observed_arr[d - 1]) / n_valid * 100
            exp_pct = benford_expected[d] * 100
            digit_distribution.append({
                "digit": d,
                "observed_pct": round(obs_pct, 3),
                "expected_pct": round(exp_pct, 3),
                "deviation": round(obs_pct - exp_pct, 3),
            })

        conform_text = "does NOT conform" if significant else "conforms"
        return json.dumps({
            "n_valid": n_valid,
            "chi2_stat": round(float(chi2_stat), 4),
            "p_value": round(float(p_value), 6),
            "significant": significant,
            "digit_distribution": digit_distribution,
            "interpretation": (
                f"{amount_col} {conform_text} to Benford's law "
                f"(χ²={chi2_stat:.2f}, p={p_value:.4f}). "
                + ("Potential data integrity issue." if significant else "Distribution appears naturally generated.")
            ),
        })


# ===========================================================================
# Registry Factory
# ===========================================================================

def advanced_registry(python_exec_timeout: int = 10) -> ToolRegistry:
    """Create a ToolRegistry with all advanced analytics tools."""
    registry = ToolRegistry()

    # Time-series
    registry.register(ComputeTimeSeriesSlopeTool())
    registry.register(ComputeAreaUnderCurveTool())
    registry.register(ComputePercentageChangeTool())
    registry.register(DetectPeaksTool())
    registry.register(DetectChangePointsTool())

    # Fraud & risk
    registry.register(ScoreFraudRiskTool())
    registry.register(DetectAmountAnomaliesTool())
    registry.register(TestTemporalFraudClusteringTool())
    registry.register(ComputeBankPairRiskTool())

    # General
    registry.register(ComputePercentileRankTool())
    registry.register(ComputeConcentrationIndexTool())
    registry.register(TestBenfordLawTool())

    # Shared with statistician
    registry.register(RunSqlTool())
    registry.register(RunPythonTool(timeout=python_exec_timeout))

    return registry
