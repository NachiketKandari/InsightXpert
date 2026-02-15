"""Statistician agent — enriches analyst SQL results with statistical analysis."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator

from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt
from insightxpert.rag.store import VectorStore

from .stat_tools import statistician_registry
from .tool_base import ToolContext, ToolRegistry

logger = logging.getLogger("insightxpert.statistician")

MAX_STATISTICIAN_ITERATIONS = 5


def _summarize_results(results: list[dict], max_rows: int = 20) -> str:
    """Create a compact text summary of analyst results for the system prompt."""
    if not results:
        return "(no data)"
    cols = list(results[0].keys())
    n = len(results)
    header = f"Columns: {cols}\nTotal rows: {n}\n"
    preview_rows = results[:max_rows]
    lines = [", ".join(f"{k}={v}" for k, v in row.items()) for row in preview_rows]
    preview = "\n".join(lines)
    if n > max_rows:
        preview += f"\n... ({n - max_rows} more rows)"
    return header + preview


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

    results_summary = _summarize_results(analyst_results)
    system_prompt = render_prompt(
        "statistician_system.j2",
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

    max_iter = config.max_statistician_iterations or MAX_STATISTICIAN_ITERATIONS

    for iteration in range(max_iter):
        logger.info("--- Statistician iteration %d/%d ---", iteration + 1, max_iter)

        llm_start = time.time()
        try:
            response = await llm.chat(messages, tools=tool_registry.get_schemas())
        except Exception as exc:
            logger.error("Statistician LLM call failed: %s", exc, exc_info=True)
            yield ChatChunk(
                type="error",
                content=f"Statistical analysis failed: {exc}",
                data={"agent": "statistician"},
                conversation_id=cid,
                timestamp=time.time(),
            )
            return
        llm_ms = (time.time() - llm_start) * 1000

        if response.tool_calls:
            tool_names = [tc.name for tc in response.tool_calls]
            logger.info("Statistician LLM (%.0fms): tool_calls=%s", llm_ms, tool_names)

            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            })

            for tc in response.tool_calls:
                yield ChatChunk(
                    type="tool_call",
                    content=f"[Statistician] Calling {tc.name}...",
                    tool_name=tc.name,
                    args=tc.arguments,
                    data={"agent": "statistician"},
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)

                yield ChatChunk(
                    type="status",
                    content=f"Running {tc.name}...",
                    data={"agent": "statistician"},
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)

                tool_start = time.time()
                result = await tool_registry.execute(
                    tc.name, tc.arguments, tool_context,
                )
                tool_ms = (time.time() - tool_start) * 1000
                logger.info("Stat tool %s (%.0fms): %s", tc.name, tool_ms, result[:200])

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                })

                yield ChatChunk(
                    type="tool_result",
                    data={"agent": "statistician", "tool": tc.name, "result": result},
                    tool_name=tc.name,
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)
        else:
            total_ms = (time.time() - loop_start) * 1000
            logger.info(
                "STATISTICIAN DONE [%s] total=%.0fms iterations=%d",
                cid, total_ms, iteration + 1,
            )

            yield ChatChunk(
                type="answer",
                content=response.content,
                data={"agent": "statistician"},
                conversation_id=cid,
                timestamp=time.time(),
            )
            break
    else:
        total_ms = (time.time() - loop_start) * 1000
        logger.warning(
            "STATISTICIAN EXHAUSTED [%s] max iterations=%d total=%.0fms",
            cid, max_iter, total_ms,
        )
        yield ChatChunk(
            type="error",
            content=f"Statistical analysis reached maximum iterations ({max_iter}).",
            data={"agent": "statistician"},
            conversation_id=cid,
            timestamp=time.time(),
        )
