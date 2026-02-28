"""Stats resolver: maps a user question to pre-computed dataset_stats rows and
formats them as a compact markdown context block for injection into the LLM prompt.

If no keywords match, returns None so there is zero overhead on unrelated questions.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("insightxpert.stats_resolver")

# (keywords_to_match, stat_groups_to_fetch)
# All keyword comparisons are done on the lowercased question.
STAT_PATTERNS: list[tuple[list[str], list[str]]] = [
    (
        ["bank", "sbi", "hdfc", "icici", "axis", "pnb", "kotak", "indusind", "yes bank", "lender"],
        ["bank"],
    ),
    (
        [
            "state", "maharashtra", "karnataka", "delhi", "gujarat", "rajasthan",
            "bengal", "telangana", "andhra", "pradesh", "uttar", "tamil",
            "geography", "region",
        ],
        ["state"],
    ),
    (
        [
            "merchant", "category", "grocery", "food", "shopping", "fuel",
            "utilities", "transport", "entertainment", "healthcare", "education",
        ],
        ["merchant_category"],
    ),
    (
        ["age", "group", "young", "senior", "elderly", "millennial", "demographic"],
        ["age_group"],
    ),
    (
        ["device", "android", "ios", "web", "mobile", "browser", "app"],
        ["device_type"],
    ),
    (
        ["network", "4g", "5g", "wifi", "wi-fi", "3g", "connectivity"],
        ["network_type"],
    ),
    (
        [
            "month", "monthly", "trend", "growth", "over time",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
            "seasonal", "quarter",
        ],
        ["monthly"],
    ),
    (
        ["hour", "time of day", "peak", "night", "morning", "evening", "afternoon", "midnight", "late"],
        ["hourly"],
    ),
    (
        [
            "fail", "failure", "failed", "declined", "decline", "error", "reject",
        ],
        ["overall", "bank", "device_type", "network_type"],
    ),
    (
        ["fraud", "flag", "flagged", "suspicious", "risk", "review"],
        ["overall", "merchant_category", "state"],
    ),
    (
        ["p2p", "p2m", "bill", "recharge", "payment type", "transaction type", "transfer"],
        ["transaction_type"],
    ),
    (
        [
            "overall", "total", "summary", "aggregate", "entire",
            "all transactions", "dataset", "how many", "count",
        ],
        ["overall"],
    ),
]

# Human-friendly headers for each stat group
_GROUP_HEADERS: dict[str, str] = {
    "overall": "Overall Dataset",
    "transaction_type": "By Transaction Type",
    "merchant_category": "By Merchant Category",
    "bank": "By Sender Bank",
    "state": "By Sender State",
    "age_group": "By Sender Age Group",
    "device_type": "By Device Type",
    "network_type": "By Network Type",
    "monthly": "Monthly Trends",
    "hourly": "Hourly Distribution",
}


def _format_value(metric: str, value: float | None, string_value: str | None) -> str:
    if string_value is not None:
        return string_value
    if value is None:
        return "N/A"
    if metric.endswith("_rate_pct") or metric.endswith("_pct"):
        return f"{value:.2f}%"
    if metric.endswith("_inr") or metric in ("avg_amount",):
        return f"₹{value:,.0f}"
    if metric.endswith("_volume_inr"):
        return f"₹{value:,.0f}"
    if metric in ("txn_count", "failure_count", "fraud_count"):
        return f"{int(value):,}"
    return f"{value:g}"


def _rows_to_markdown(group: str, rows: list[dict]) -> str:
    """Convert a list of stat rows for one group to a compact markdown table."""
    if not rows:
        return ""

    # Separate rows by dimension
    # structure: { dimension: { metric: (value, string_value) } }
    by_dim: dict[str | None, dict[str, tuple]] = defaultdict(dict)
    for row in rows:
        dim = row["dimension"]
        metric = row["metric"]
        by_dim[dim][metric] = (row["value"], row["string_value"])

    header = _GROUP_HEADERS.get(group, group)

    # For overall (single None dimension), render as key-value list
    if list(by_dim.keys()) == [None]:
        lines = [f"### {header}"]
        for metric, (val, sval) in by_dim[None].items():
            nice_metric = metric.replace("_", " ").title()
            lines.append(f"- **{nice_metric}**: {_format_value(metric, val, sval)}")
        return "\n".join(lines)

    # Multi-dimension: render as a table
    # Collect all metric names (in insertion order)
    all_metrics: list[str] = []
    seen: set[str] = set()
    for dim_metrics in by_dim.values():
        for m in dim_metrics:
            if m not in seen:
                all_metrics.append(m)
                seen.add(m)

    nice_metrics = [m.replace("_", " ").title() for m in all_metrics]
    # Table header
    header_row = "| Dimension | " + " | ".join(nice_metrics) + " |"
    sep_row = "|-----------|" + "|".join("---" for _ in nice_metrics) + "|"
    lines = [f"### {header}", header_row, sep_row]
    for dim, dim_metrics in by_dim.items():
        cells = [str(dim) if dim is not None else "—"]
        for metric in all_metrics:
            val, sval = dim_metrics.get(metric, (None, None))
            cells.append(_format_value(metric, val, sval))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


@dataclass
class StatsResult:
    """Holds resolved stats context: the markdown for the LLM and the matched group names."""

    markdown: str
    groups: list[str] = field(default_factory=list)


class StatsResolver:
    """Resolves a user question to pre-computed stat rows from dataset_stats."""

    def resolve(self, question: str, engine: Engine) -> StatsResult | None:
        """Return a StatsResult with markdown and matched groups, or None."""
        q_lower = question.lower()

        matched_groups: list[str] = []
        seen: set[str] = set()
        for keywords, groups in STAT_PATTERNS:
            if any(kw in q_lower for kw in keywords):
                for g in groups:
                    if g not in seen:
                        matched_groups.append(g)
                        seen.add(g)

        if not matched_groups:
            logger.debug("StatsResolver: no groups matched for question: %s", question[:80])
            return None

        logger.info("StatsResolver matched groups: %s", matched_groups)

        placeholders = ", ".join(f"'{g}'" for g in matched_groups)
        sql = (
            f"SELECT stat_group, dimension, metric, value, string_value "
            f"FROM dataset_stats "
            f"WHERE stat_group IN ({placeholders}) "
            f"ORDER BY stat_group, dimension, metric"
        )

        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
        except Exception as e:
            logger.warning("StatsResolver DB read failed: %s", e)
            return None

        if not rows:
            logger.debug("StatsResolver: no rows found in dataset_stats for groups %s", matched_groups)
            return None

        # Group rows by stat_group, preserving matched order
        by_group: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_group[row["stat_group"]].append(row)

        sections: list[str] = []
        for group in matched_groups:
            group_rows = by_group.get(group, [])
            if group_rows:
                md = _rows_to_markdown(group, group_rows)
                if md:
                    sections.append(md)

        if not sections:
            return None

        return StatsResult(markdown="\n\n".join(sections), groups=matched_groups)
