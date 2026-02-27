"""Statistician agent — enriches analyst SQL results with statistical analysis."""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt
from insightxpert.rag.store import VectorStore

from .common import agent_tool_loop, summarize_results
from .stat_tools import statistician_registry
from .tool_base import ToolContext, ToolRegistry

logger = logging.getLogger("insightxpert.statistician")


async def statistician_loop(
    question: str,
    analyst_results: list[dict],
    analyst_sql: str,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str = "",
    tool_registry: ToolRegistry | None = None,
) -> AsyncGenerator[ChatChunk, None]:
    """Run the statistician agent loop on analyst results."""
    cid = conversation_id
    loop_start = time.time()

    if tool_registry is None:
        timeout = config.python_exec_timeout_seconds
        tool_registry = statistician_registry(timeout=timeout)

    tool_context = ToolContext(
        db=db,
        rag=rag,
        row_limit=config.sql_row_limit,
        analyst_results=analyst_results,
        analyst_sql=analyst_sql,
    )

    logger.info("=" * 60)
    logger.info("STATISTICIAN [%s]: processing %d analyst rows", cid, len(analyst_results))
    logger.info("=" * 60)

    yield ChatChunk(
        type="status",
        content="Running statistical analysis on query results...",
        data={"agent": "statistician"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    results_summary = summarize_results(analyst_results)
    system_prompt = render_prompt(
        "statistician_system.j2",
        engine=db.engine,
        analyst_sql=analyst_sql or "(no SQL)",
        results_summary=results_summary,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"The analyst answered: \"{question}\"\n\n"
                f"Perform statistical analysis on the results. "
                f"Identify patterns, test hypotheses, and quantify the strength of evidence."
            ),
        },
    ]

    async for chunk in agent_tool_loop(
        agent_name="statistician",
        messages=messages,
        tool_registry=tool_registry,
        tool_context=tool_context,
        llm=llm,
        max_iter=config.max_statistician_iterations,
        conversation_id=cid,
        loop_start=loop_start,
    ):
        yield chunk
