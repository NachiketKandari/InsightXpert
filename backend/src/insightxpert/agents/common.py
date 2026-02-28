"""Shared utilities for agent loops."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator

from insightxpert.api.models import ChatChunk
from insightxpert.llm.base import LLMProvider

from .tool_base import ToolContext, ToolRegistry

logger = logging.getLogger("insightxpert.agents.common")


def summarize_results(results: list[dict], max_rows: int = 20) -> str:
    """Create a compact text summary of analyst results for the system prompt."""
    if not results:
        return "(no data)"
    cols = list(results[0].keys())
    n = len(results)
    header = (
        f"**AVAILABLE COLUMNS (use these EXACT names):** {cols}\n"
        f"Total rows: {n}\n"
    )
    preview_rows = results[:max_rows]
    lines = [", ".join(f"{k}={str(v)[:50]}" for k, v in row.items()) for row in preview_rows]
    preview = "\n".join(lines)
    if n > max_rows:
        preview += f"\n... ({n - max_rows} more rows)"
    return header + preview


async def agent_tool_loop(
    *,
    agent_name: str,
    messages: list[dict],
    tool_registry: ToolRegistry,
    tool_context: ToolContext,
    llm: LLMProvider,
    max_iter: int,
    conversation_id: str,
    loop_start: float,
) -> AsyncGenerator[ChatChunk, None]:
    """Shared agent tool-call loop.

    Runs the LLM → tool-call → tool-result cycle up to max_iter times,
    yielding ChatChunk events. Breaks on a text-only response (answer).
    Yields an error chunk if max iterations are exhausted.
    """
    cid = conversation_id

    for iteration in range(max_iter):
        logger.info("--- %s iteration %d/%d ---", agent_name.title(), iteration + 1, max_iter)

        llm_start = time.time()
        try:
            response = await llm.chat(messages, tools=tool_registry.get_schemas())
        except Exception as exc:
            logger.error("%s LLM call failed: %s", agent_name, exc, exc_info=True)
            yield ChatChunk(
                type="error",
                content=f"{agent_name.title()} failed: {exc}",
                data={"agent": agent_name},
                conversation_id=cid,
                timestamp=time.time(),
            )
            return
        llm_ms = (time.time() - llm_start) * 1000

        if response.tool_calls:
            tool_names = [tc.name for tc in response.tool_calls]
            logger.info("%s LLM (%.0fms): tool_calls=%s", agent_name, llm_ms, tool_names)

            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            })

            for tc in response.tool_calls:
                yield ChatChunk(
                    type="tool_call",
                    content=f"[{agent_name.title()}] Calling {tc.name}...",
                    tool_name=tc.name,
                    args=tc.arguments,
                    data={"agent": agent_name},
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)

                yield ChatChunk(
                    type="status",
                    content=f"Running {tc.name}...",
                    data={"agent": agent_name},
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)

                tool_start = time.time()
                result = await tool_registry.execute(tc.name, tc.arguments, tool_context)
                tool_ms = (time.time() - tool_start) * 1000
                logger.info("%s tool %s (%.0fms): %s", agent_name, tc.name, tool_ms, result[:200])

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                })

                yield ChatChunk(
                    type="tool_result",
                    data={"agent": agent_name, "tool": tc.name, "result": result},
                    tool_name=tc.name,
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)
        else:
            total_ms = (time.time() - loop_start) * 1000
            logger.info(
                "%s DONE [%s] total=%.0fms iterations=%d",
                agent_name.upper(), cid, total_ms, iteration + 1,
            )
            yield ChatChunk(
                type="answer",
                content=response.content,
                data={"agent": agent_name},
                conversation_id=cid,
                timestamp=time.time(),
            )
            break
    else:
        total_ms = (time.time() - loop_start) * 1000
        logger.warning(
            "%s EXHAUSTED [%s] max iterations=%d total=%.0fms",
            agent_name.upper(), cid, max_iter, total_ms,
        )
        yield ChatChunk(
            type="error",
            content=f"{agent_name.title()} reached maximum iterations ({max_iter}).",
            data={"agent": agent_name},
            conversation_id=cid,
            timestamp=time.time(),
        )
