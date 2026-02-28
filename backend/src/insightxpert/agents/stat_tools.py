"""Statistical analysis tools for the statistician agent."""

from __future__ import annotations

import json
import logging
import math
import signal
import traceback
from contextlib import contextmanager
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from insightxpert.agents.tool_base import Tool, ToolContext, ToolRegistry
from insightxpert.agents.tools import RunSqlTool

logger = logging.getLogger("insightxpert.stat_tools")


def _get_analyst_df(context: ToolContext) -> pd.DataFrame:
    """Convert analyst_results (list[dict]) to a DataFrame."""
    if not context.analyst_results:
        return pd.DataFrame()
    return pd.DataFrame(context.analyst_results)


@contextmanager
def _timeout(seconds: int):
    """Context manager that raises TimeoutError after *seconds* on Unix."""
    def _handler(signum, frame):
        raise TimeoutError(f"Execution timed out after {seconds}s")

    try:
        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
        yield
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    except (AttributeError, ValueError):
        # AttributeError: Windows (no SIGALRM)
        # ValueError: non-main thread (Cloud Run / gunicorn workers)
        yield


# ---------------------------------------------------------------------------
# 1. RunPythonTool
# ---------------------------------------------------------------------------

_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool,
    "dict": dict, "enumerate": enumerate, "filter": filter,
    "float": float, "frozenset": frozenset, "int": int,
    "isinstance": isinstance, "len": len, "list": list,
    "map": map, "max": max, "min": min, "print": print,
    "range": range, "reversed": reversed, "round": round,
    "set": set, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "True": True, "False": False, "None": None,
    # Common exceptions
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "ZeroDivisionError": ZeroDivisionError,
    "RuntimeError": RuntimeError, "StopIteration": StopIteration,
}


class RunPythonTool(Tool):
    """Execute Python code with numpy, pandas, scipy.stats pre-loaded."""

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "run_python"

    @property
    def description(self) -> str:
        return (
            "Execute a Python code snippet for statistical analysis. "
            "Pre-loaded: np (numpy), pd (pandas), stats (scipy.stats), math, "
            "and df (analyst query results as a DataFrame). "
            "Print your results — the captured stdout is returned."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                }
            },
            "required": ["code"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        code = args["code"]
        df = _get_analyst_df(context)

        namespace: dict[str, Any] = {
            "__builtins__": _SAFE_BUILTINS,
            "np": np,
            "pd": pd,
            "stats": stats,
            "math": math,
            "df": df,
        }

        captured: list[str] = []

        def _print(*a, **kw):
            import io
            buf = io.StringIO()
            print(*a, file=buf, **kw)
            captured.append(buf.getvalue())

        namespace["print"] = _print

        try:
            with _timeout(self._timeout):
                exec(compile(code, "<statistician>", "exec"), namespace)  # noqa: S102
        except TimeoutError:
            return json.dumps({"error": f"Code execution timed out after {self._timeout}s"})
        except Exception as e:
            logger.warning("RunPython execution failed: %s", e, exc_info=True)
            return json.dumps({"error": traceback.format_exc()[-1500:]})

        output = "".join(captured).strip()
        return json.dumps({"output": output or "(no output)"})


# ---------------------------------------------------------------------------
# 2. ComputeDescriptiveStatsTool
# ---------------------------------------------------------------------------

class ComputeDescriptiveStatsTool(Tool):
    @property
    def name(self) -> str:
        return "compute_descriptive_stats"

    @property
    def description(self) -> str:
        return (
            "Compute descriptive statistics for a numeric column in the analyst results: "
            "count, mean, std, min, Q1, median, Q3, max, skewness, kurtosis."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "column": {
                    "type": "string",
                    "description": "Column name to analyze",
                }
            },
            "required": ["column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _get_analyst_df(context)
        col = args["column"]
        if col not in df.columns:
            return json.dumps({"error": f"Column '{col}' not found. Available: {list(df.columns)}"})

        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            return json.dumps({"error": f"Column '{col}' has no numeric values"})

        result = {
            "column": col,
            "count": int(series.count()),
            "mean": round(float(series.mean()), 4),
            "std": round(float(series.std()), 4),
            "min": round(float(series.min()), 4),
            "q1": round(float(series.quantile(0.25)), 4),
            "median": round(float(series.median()), 4),
            "q3": round(float(series.quantile(0.75)), 4),
            "max": round(float(series.max()), 4),
            "skewness": round(float(stats.skew(series)), 4),
            "kurtosis": round(float(stats.kurtosis(series)), 4),
        }
        return json.dumps(result)


# ---------------------------------------------------------------------------
# 3. TestHypothesisTool
# ---------------------------------------------------------------------------

class TestHypothesisTool(Tool):
    @property
    def name(self) -> str:
        return "test_hypothesis"

    @property
    def description(self) -> str:
        return (
            "Run a statistical hypothesis test on the analyst results. "
            "Supported tests: chi_squared, t_test, mann_whitney, anova, z_proportion."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "test": {
                    "type": "string",
                    "enum": ["chi_squared", "t_test", "mann_whitney", "anova", "z_proportion"],
                    "description": "Statistical test to run",
                },
                "column": {
                    "type": "string",
                    "description": "Primary numeric column",
                },
                "group_column": {
                    "type": "string",
                    "description": "Column to split groups (for t_test, mann_whitney, anova)",
                },
                "group_a": {
                    "type": "string",
                    "description": "Value for group A (t_test, mann_whitney)",
                },
                "group_b": {
                    "type": "string",
                    "description": "Value for group B (t_test, mann_whitney)",
                },
                "category_col_1": {
                    "type": "string",
                    "description": "First categorical column (chi_squared)",
                },
                "category_col_2": {
                    "type": "string",
                    "description": "Second categorical column (chi_squared)",
                },
                "count_success": {"type": "integer", "description": "Successes (z_proportion)"},
                "count_total": {"type": "integer", "description": "Total trials (z_proportion)"},
                "hypothesized_proportion": {"type": "number", "description": "H0 proportion (z_proportion, default 0.5)"},
            },
            "required": ["test"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _get_analyst_df(context)
        test = args["test"]

        try:
            if test == "chi_squared":
                return self._chi_squared(df, args)
            elif test == "t_test":
                return self._t_test(df, args)
            elif test == "mann_whitney":
                return self._mann_whitney(df, args)
            elif test == "anova":
                return self._anova(df, args)
            elif test == "z_proportion":
                return self._z_proportion(args)
            else:
                return json.dumps({"error": f"Unknown test: {test}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _chi_squared(self, df: pd.DataFrame, args: dict) -> str:
        c1, c2 = args.get("category_col_1", ""), args.get("category_col_2", "")
        if not c1 or not c2:
            return json.dumps({"error": "chi_squared requires category_col_1 and category_col_2"})
        ct = pd.crosstab(df[c1], df[c2])
        chi2, p, dof, _ = stats.chi2_contingency(ct)
        n = ct.values.sum()
        cramers_v = math.sqrt(chi2 / (n * (min(ct.shape) - 1))) if n > 0 and min(ct.shape) > 1 else 0.0
        return json.dumps({
            "test": "chi_squared",
            "statistic": round(float(chi2), 4),
            "p_value": round(float(p), 6),
            "dof": int(dof),
            "effect_size_cramers_v": round(float(cramers_v), 4),
            "significant_at_005": bool(p < 0.05),
        })

    def _t_test(self, df: pd.DataFrame, args: dict) -> str:
        col = args.get("column", "")
        gcol = args.get("group_column", "")
        ga, gb = args.get("group_a", ""), args.get("group_b", "")
        if not all([col, gcol, ga, gb]):
            return json.dumps({"error": "t_test requires column, group_column, group_a, group_b"})
        a = pd.to_numeric(df.loc[df[gcol].astype(str) == ga, col], errors="coerce").dropna()
        b = pd.to_numeric(df.loc[df[gcol].astype(str) == gb, col], errors="coerce").dropna()
        if len(a) < 2 or len(b) < 2:
            return json.dumps({"error": f"Need at least 2 values per group (got {len(a)}, {len(b)})"})
        t_stat, p = stats.ttest_ind(a, b, equal_var=False)
        pooled_std = math.sqrt((a.std() ** 2 + b.std() ** 2) / 2)
        cohens_d = (a.mean() - b.mean()) / pooled_std if pooled_std > 0 else 0.0
        return json.dumps({
            "test": "t_test",
            "statistic": round(float(t_stat), 4),
            "p_value": round(float(p), 6),
            "effect_size_cohens_d": round(float(cohens_d), 4),
            "group_a_mean": round(float(a.mean()), 4),
            "group_b_mean": round(float(b.mean()), 4),
            "group_a_n": len(a),
            "group_b_n": len(b),
            "significant_at_005": float(p) < 0.05,
        })

    def _mann_whitney(self, df: pd.DataFrame, args: dict) -> str:
        col = args.get("column", "")
        gcol = args.get("group_column", "")
        ga, gb = args.get("group_a", ""), args.get("group_b", "")
        if not all([col, gcol, ga, gb]):
            return json.dumps({"error": "mann_whitney requires column, group_column, group_a, group_b"})
        a = pd.to_numeric(df.loc[df[gcol].astype(str) == ga, col], errors="coerce").dropna()
        b = pd.to_numeric(df.loc[df[gcol].astype(str) == gb, col], errors="coerce").dropna()
        if len(a) < 1 or len(b) < 1:
            return json.dumps({"error": "Need at least 1 value per group"})
        u_stat, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        n = len(a) * len(b)
        r = 1 - (2 * u_stat) / n if n > 0 else 0.0
        return json.dumps({
            "test": "mann_whitney",
            "statistic": round(float(u_stat), 4),
            "p_value": round(float(p), 6),
            "effect_size_r": round(float(r), 4),
            "group_a_n": len(a),
            "group_b_n": len(b),
            "significant_at_005": float(p) < 0.05,
        })

    def _anova(self, df: pd.DataFrame, args: dict) -> str:
        col = args.get("column", "")
        gcol = args.get("group_column", "")
        if not col or not gcol:
            return json.dumps({"error": "anova requires column and group_column"})
        groups = []
        group_names = df[gcol].dropna().unique()
        for name in group_names:
            g = pd.to_numeric(df.loc[df[gcol] == name, col], errors="coerce").dropna()
            if len(g) >= 2:
                groups.append(g)
        if len(groups) < 2:
            return json.dumps({"error": "Need at least 2 groups with 2+ values each"})
        f_stat, p = stats.f_oneway(*groups)
        grand_mean = pd.concat(groups).mean()
        ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
        ss_total = sum(((g - grand_mean) ** 2).sum() for g in groups)
        eta_sq = ss_between / ss_total if ss_total > 0 else 0.0
        return json.dumps({
            "test": "anova",
            "statistic": round(float(f_stat), 4),
            "p_value": round(float(p), 6),
            "effect_size_eta_squared": round(float(eta_sq), 4),
            "num_groups": len(groups),
            "significant_at_005": float(p) < 0.05,
        })

    def _z_proportion(self, args: dict) -> str:
        successes = args.get("count_success", 0)
        total = args.get("count_total", 0)
        p0 = args.get("hypothesized_proportion", 0.5)
        if total == 0:
            return json.dumps({"error": "count_total must be > 0"})
        p_hat = successes / total
        se = math.sqrt(p0 * (1 - p0) / total)
        z = (p_hat - p0) / se if se > 0 else 0.0
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))
        return json.dumps({
            "test": "z_proportion",
            "statistic": round(z, 4),
            "p_value": round(float(p_value), 6),
            "observed_proportion": round(p_hat, 4),
            "hypothesized_proportion": p0,
            "sample_size": total,
            "significant_at_005": float(p_value) < 0.05,
        })


# ---------------------------------------------------------------------------
# 4. ComputeCorrelationTool
# ---------------------------------------------------------------------------

class ComputeCorrelationTool(Tool):
    @property
    def name(self) -> str:
        return "compute_correlation"

    @property
    def description(self) -> str:
        return (
            "Compute correlation between two numeric columns. "
            "Methods: pearson, spearman, kendall."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "column_x": {"type": "string", "description": "First numeric column"},
                "column_y": {"type": "string", "description": "Second numeric column"},
                "method": {
                    "type": "string",
                    "enum": ["pearson", "spearman", "kendall"],
                    "description": "Correlation method (default: pearson)",
                },
            },
            "required": ["column_x", "column_y"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _get_analyst_df(context)
        cx, cy = args["column_x"], args["column_y"]
        method = args.get("method", "pearson")

        for c in (cx, cy):
            if c not in df.columns:
                return json.dumps({"error": f"Column '{c}' not found. Available: {list(df.columns)}"})

        x = pd.to_numeric(df[cx], errors="coerce")
        y = pd.to_numeric(df[cy], errors="coerce")
        valid = x.notna() & y.notna()
        x, y = x[valid], y[valid]

        if len(x) < 3:
            return json.dumps({"error": f"Need at least 3 valid pairs (got {len(x)})"})

        if method == "pearson":
            r, p = stats.pearsonr(x, y)
        elif method == "spearman":
            r, p = stats.spearmanr(x, y)
        elif method == "kendall":
            r, p = stats.kendalltau(x, y)
        else:
            return json.dumps({"error": f"Unknown method: {method}"})

        return json.dumps({
            "method": method,
            "column_x": cx,
            "column_y": cy,
            "correlation": round(float(r), 4),
            "p_value": round(float(p), 6),
            "n": len(x),
            "significant_at_005": float(p) < 0.05,
        })


# ---------------------------------------------------------------------------
# 5. FitDistributionTool
# ---------------------------------------------------------------------------

class FitDistributionTool(Tool):
    @property
    def name(self) -> str:
        return "fit_distribution"

    @property
    def description(self) -> str:
        return (
            "Fit statistical distributions to a numeric column and rank by KS-test p-value. "
            "Tries: normal, exponential, lognormal, gamma, weibull_min."
        )

    def get_args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "column": {
                    "type": "string",
                    "description": "Numeric column to fit distributions to",
                }
            },
            "required": ["column"],
        }

    async def execute(self, context: ToolContext, args: dict) -> str:
        df = _get_analyst_df(context)
        col = args["column"]
        if col not in df.columns:
            return json.dumps({"error": f"Column '{col}' not found. Available: {list(df.columns)}"})

        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 5:
            return json.dumps({"error": f"Need at least 5 values (got {len(series)})"})

        candidates = {
            "normal": stats.norm,
            "exponential": stats.expon,
            "lognormal": stats.lognorm,
            "gamma": stats.gamma,
            "weibull_min": stats.weibull_min,
        }

        data = series.values
        fits = []
        for dist_name, dist in candidates.items():
            try:
                params = dist.fit(data)
                ks_stat, ks_p = stats.kstest(data, dist_name, args=params)
                fits.append({
                    "distribution": dist_name,
                    "ks_statistic": round(float(ks_stat), 4),
                    "ks_p_value": round(float(ks_p), 6),
                    "params": [round(float(p), 4) for p in params],
                })
            except Exception as e:
                logger.debug("Distribution fit failed for %s: %s", dist_name, e)
                continue

        fits.sort(key=lambda x: x["ks_p_value"], reverse=True)
        best = fits[0]["distribution"] if fits else None

        return json.dumps({
            "column": col,
            "n": len(series),
            "best_fit": best,
            "fits": fits,
        })


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def statistician_registry(timeout: int = 10) -> ToolRegistry:
    """Create a ToolRegistry with all statistician tools."""
    registry = ToolRegistry()
    registry.register(RunPythonTool(timeout=timeout))
    registry.register(ComputeDescriptiveStatsTool())
    registry.register(TestHypothesisTool())
    registry.register(ComputeCorrelationTool())
    registry.register(FitDistributionTool())
    registry.register(RunSqlTool())
    return registry
