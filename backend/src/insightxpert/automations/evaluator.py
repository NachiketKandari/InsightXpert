from __future__ import annotations

import logging

logger = logging.getLogger("insightxpert.automations.evaluator")

OPERATORS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


class TriggerEvaluator:
    """Evaluates trigger conditions against SQL query results."""

    def evaluate(
        self,
        conditions: list[dict],
        result: dict,
        previous_result: dict | None = None,
        previous_results: list[dict] | None = None,
    ) -> list[dict]:
        """Evaluate all conditions. Returns list of TriggerResult dicts.

        Args:
            conditions: List of trigger condition dicts.
            result: Current run result {columns, rows}.
            previous_result: Most recent previous run result (for change_detection).
            previous_results: Multiple previous run results ordered newest-first (for slope).
        """
        results = []
        for cond in conditions:
            tr = self._evaluate_one(cond, result, previous_result, previous_results)
            results.append(tr)
        return results

    def any_fired(self, trigger_results: list[dict]) -> bool:
        return any(r["fired"] for r in trigger_results)

    def _evaluate_one(
        self,
        condition: dict,
        result: dict,
        previous_result: dict | None,
        previous_results: list[dict] | None = None,
    ) -> dict:
        cond_type = condition.get("type", "")
        try:
            if cond_type == "threshold":
                return self._eval_threshold(condition, result)
            elif cond_type == "change_detection":
                return self._eval_change_detection(condition, result, previous_result)
            elif cond_type == "row_count":
                return self._eval_row_count(condition, result)
            elif cond_type == "column_expression":
                return self._eval_column_expression(condition, result)
            elif cond_type == "slope":
                return self._eval_slope(condition, result, previous_results)
            else:
                return {"condition": condition, "fired": False, "actual_value": None, "message": f"Unknown trigger type: {cond_type}"}
        except Exception as e:
            logger.error("Trigger evaluation error: %s", e)
            return {"condition": condition, "fired": False, "actual_value": None, "message": f"Error: {e}"}

    def _extract_scalar(self, result: dict, column: str | None = None) -> float | None:
        """Extract a scalar value from the result."""
        rows = result.get("rows", [])
        columns = result.get("columns", [])
        if not rows:
            return None
        first_row = rows[0]

        if column and column in first_row:
            val = first_row[column]
            return float(val) if val is not None else None

        # Heuristic: if 1 row and 1 numeric column, use that
        numeric_cols = []
        for col in columns:
            val = first_row.get(col)
            if val is not None:
                try:
                    float(val)
                    numeric_cols.append(col)
                except (ValueError, TypeError):
                    pass

        if len(numeric_cols) == 1:
            return float(first_row[numeric_cols[0]])
        elif numeric_cols:
            return float(first_row[numeric_cols[0]])
        return None

    def _eval_threshold(self, condition: dict, result: dict) -> dict:
        column = condition.get("column")
        operator = condition.get("operator", "gt")
        threshold = condition.get("value")

        if threshold is None:
            return {"condition": condition, "fired": False, "actual_value": None, "message": "No threshold value specified"}

        actual = self._extract_scalar(result, column)
        if actual is None:
            return {"condition": condition, "fired": False, "actual_value": None, "message": "Could not extract scalar value"}

        op_fn = OPERATORS.get(operator)
        if not op_fn:
            return {"condition": condition, "fired": False, "actual_value": actual, "message": f"Unknown operator: {operator}"}

        fired = op_fn(actual, threshold)
        op_symbol = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==", "ne": "!="}
        msg = f"Value {actual} {op_symbol.get(operator, operator)} {threshold}" if fired else f"Value {actual} did not meet threshold {op_symbol.get(operator, operator)} {threshold}"
        return {"condition": condition, "fired": fired, "actual_value": actual, "message": msg}

    def _eval_change_detection(self, condition: dict, result: dict, previous_result: dict | None) -> dict:
        if previous_result is None:
            return {"condition": condition, "fired": False, "actual_value": None, "message": "No previous run for comparison"}

        column = condition.get("column")
        change_pct = condition.get("change_percent", 10.0)

        current = self._extract_scalar(result, column)
        previous = self._extract_scalar(previous_result, column)

        if current is None or previous is None:
            return {"condition": condition, "fired": False, "actual_value": current, "message": "Could not extract values for comparison"}

        if previous == 0:
            pct_change = 100.0 if current != 0 else 0.0
        else:
            pct_change = abs((current - previous) / previous) * 100

        fired = pct_change >= change_pct
        msg = f"Changed {pct_change:.1f}% (from {previous} to {current})" if fired else f"Changed only {pct_change:.1f}% (threshold: {change_pct}%)"
        return {"condition": condition, "fired": fired, "actual_value": pct_change, "message": msg}

    def _eval_row_count(self, condition: dict, result: dict) -> dict:
        operator = condition.get("operator", "gt")
        threshold = condition.get("value", 0)
        rows = result.get("rows", [])
        actual = len(rows)

        op_fn = OPERATORS.get(operator)
        if not op_fn:
            return {"condition": condition, "fired": False, "actual_value": actual, "message": f"Unknown operator: {operator}"}

        fired = op_fn(actual, threshold)
        msg = f"Row count {actual} triggered (threshold: {operator} {threshold})" if fired else f"Row count {actual} did not trigger (threshold: {operator} {threshold})"
        return {"condition": condition, "fired": fired, "actual_value": actual, "message": msg}

    def _eval_column_expression(self, condition: dict, result: dict) -> dict:
        column = condition.get("column")
        operator = condition.get("operator", "gt")
        threshold = condition.get("value")
        scope = condition.get("scope", "any_row")

        if not column or threshold is None:
            return {"condition": condition, "fired": False, "actual_value": None, "message": "Column and value required"}

        rows = result.get("rows", [])
        if not rows:
            return {"condition": condition, "fired": False, "actual_value": None, "message": "No rows to evaluate"}

        op_fn = OPERATORS.get(operator)
        if not op_fn:
            return {"condition": condition, "fired": False, "actual_value": None, "message": f"Unknown operator: {operator}"}

        matches = 0
        for row in rows:
            val = row.get(column)
            if val is not None:
                try:
                    if op_fn(float(val), threshold):
                        matches += 1
                except (ValueError, TypeError):
                    pass

        if scope == "all_rows":
            fired = matches == len(rows) and len(rows) > 0
        else:  # any_row
            fired = matches > 0

        msg = f"{matches}/{len(rows)} rows matched ({scope})" if fired else f"Only {matches}/{len(rows)} rows matched ({scope})"
        return {"condition": condition, "fired": fired, "actual_value": matches, "message": msg}

    def _eval_slope(self, condition: dict, result: dict, previous_results: list[dict] | None) -> dict:
        """Calculate slope (rate of change) across recent runs.

        Uses simple linear regression over the scalar values from the current
        run and N previous runs. Fires when the slope's absolute value (or
        directional value) exceeds the threshold.
        """
        column = condition.get("column")
        operator = condition.get("operator", "gt")
        threshold = condition.get("value")
        window = condition.get("slope_window", 5)

        if threshold is None:
            return {"condition": condition, "fired": False, "actual_value": None, "message": "No threshold value specified for slope"}

        # Build data points: current result is the most recent, then previous_results
        # Points are ordered oldest-first for regression (index = time axis).
        data_points: list[float] = []
        if previous_results:
            # previous_results is newest-first, reverse so oldest is first
            for prev in reversed(previous_results[:window]):
                val = self._extract_scalar(prev, column)
                if val is not None:
                    data_points.append(val)

        current = self._extract_scalar(result, column)
        if current is not None:
            data_points.append(current)

        if len(data_points) < 2:
            return {
                "condition": condition,
                "fired": False,
                "actual_value": None,
                "message": f"Need at least 2 data points for slope (have {len(data_points)})",
            }

        # Simple linear regression: slope = Σ((xi - x̄)(yi - ȳ)) / Σ((xi - x̄)²)
        n = len(data_points)
        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = sum(data_points) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, data_points))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        op_fn = OPERATORS.get(operator)
        if not op_fn:
            return {"condition": condition, "fired": False, "actual_value": slope, "message": f"Unknown operator: {operator}"}

        fired = op_fn(slope, threshold)
        direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
        op_symbol = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==", "ne": "!="}
        msg = (
            f"Slope {slope:.4f} ({direction}, {n} points) "
            f"{'triggered' if fired else 'did not trigger'} "
            f"({op_symbol.get(operator, operator)} {threshold})"
        )
        return {"condition": condition, "fired": fired, "actual_value": round(slope, 6), "message": msg}
