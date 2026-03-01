"""Quant analyst agent — merges statistical + advanced analytics tools.

Used as a downstream agent in the multi-agent orchestrator when a sub-task
requires quantitative analysis beyond SQL. Combines all tools from the
statistician and advanced agent into a single registry, receives upstream
SQL analyst results as context, and runs an agentic tool loop.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

from insightxpert.agents.dag_executor import SubTaskResult
from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt
from insightxpert.rag.store import VectorStore

from .advanced_tools import advanced_registry
from .common import agent_tool_loop, summarize_results
from .stat_tools import (
    ComputeCorrelationTool,
    ComputeDescriptiveStatsTool,
    FitDistributionTool,
    TestHypothesisTool,
)
from .tool_base import ToolContext, ToolRegistry

logger = logging.getLogger("insightxpert.quant_analyst")


def _quant_registry(python_exec_timeout: int = 10) -> ToolRegistry:
    """Create a ToolRegistry with all stat + advanced tools merged.

    The advanced_registry already includes run_sql and run_python, so we
    only add the stat-specific tools that aren't in the advanced set.
    """
    registry = advanced_registry(python_exec_timeout=python_exec_timeout)

    # Add stat tools not already in the advanced registry
    registry.register(ComputeDescriptiveStatsTool())
    registry.register(TestHypothesisTool())
    registry.register(ComputeCorrelationTool())
    registry.register(FitDistributionTool())

    return registry


async def quant_analyst_loop(
    task: str,
    upstream_results: dict[str, SubTaskResult],
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str = "",
    ddl: str = "",
    documentation: str = "",
) -> AsyncGenerator[ChatChunk, None]:
    """Run the quant analyst agent loop on upstream results."""
    cid = conversation_id
    loop_start = time.time()

    tool_registry = _quant_registry(python_exec_timeout=config.python_exec_timeout_seconds)

    # Merge upstream analyst results into a single dataset for the tool context
    merged_results: list[dict] = []
    merged_sql: str = ""
    upstream_summary_lines: list[str] = []

    for task_id, result in upstream_results.items():
        if result.success and result.rows:
            merged_results.extend(result.rows)
            if result.sql:
                merged_sql = result.sql
            upstream_summary_lines.append(
                f"### Source [{task_id}]\n"
                f"**SQL:** `{result.sql or '(none)'}`\n"
                f"**Rows:** {len(result.rows)}\n"
                f"**Answer:** {result.answer[:300] if result.answer else '(none)'}"
            )

    if not merged_results:
        yield ChatChunk(
            type="error",
            content="Quant analyst received no data from upstream tasks.",
            data={"agent": "quant_analyst"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        return

    tool_context = ToolContext(
        db=db,
        rag=rag,
        row_limit=config.sql_row_limit,
        analyst_results=merged_results,
        analyst_sql=merged_sql,
    )

    logger.info("=" * 60)
    logger.info("QUANT ANALYST [%s]: processing %d rows from %d upstream tasks",
                cid, len(merged_results), len(upstream_results))
    logger.info("=" * 60)

    yield ChatChunk(
        type="status",
        content="Running quantitative analysis...",
        data={"agent": "quant_analyst"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    results_summary = summarize_results(merged_results)
    upstream_context = "\n\n".join(upstream_summary_lines) if upstream_summary_lines else "(no upstream data)"

    system_prompt = render_prompt(
        "quant_analyst_system.j2",
        engine=db.engine,
        ddl=ddl,
        documentation=documentation,
        analyst_sql=merged_sql or "(no SQL)",
        results_summary=results_summary,
        upstream_context=upstream_context,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                f"Apply quantitative analysis to the upstream data. "
                f"Use the most appropriate tool(s) for the question — "
                f"time-series tools for temporal data, fraud tools for risk analysis, "
                f"hypothesis tests for comparisons, or general tools for segment benchmarking."
            ),
        },
    ]

    async for chunk in agent_tool_loop(
        agent_name="quant_analyst",
        messages=messages,
        tool_registry=tool_registry,
        tool_context=tool_context,
        llm=llm,
        max_iter=config.max_quant_analyst_iterations,
        conversation_id=cid,
        loop_start=loop_start,
    ):
        yield chunk
