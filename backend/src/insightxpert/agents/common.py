"""Shared utilities for agent loops."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Awaitable, Callable

from insightxpert.agents.dag_executor import (
    OrchestratorPlan,
    OriginalAnalystResult,
    SubTask,
    SubTaskResult,
)
from insightxpert.api.models import ChatChunk
from insightxpert.llm.base import LLMProvider

from .tool_base import ToolContext, ToolRegistry

logger = logging.getLogger("insightxpert.agents.common")


def strip_json_fences(raw: str) -> str:
    """Strip markdown ```json fences from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    return raw


def make_plan_chunk(
    plan: OrchestratorPlan, content: str, conversation_id: str,
) -> ChatChunk:
    """Build a ChatChunk for an orchestrator_plan event."""
    return ChatChunk(
        type="orchestrator_plan",
        data={
            "reasoning": plan.reasoning,
            "tasks": [
                {
                    "id": t.id,
                    "agent": t.agent,
                    "task": t.task,
                    "depends_on": t.depends_on,
                    "category": t.category,
                }
                for t in plan.tasks
            ],
        },
        content=content,
        conversation_id=conversation_id,
        timestamp=time.time(),
    )


# Shared enrichment category labels — used by orchestrator, deep_think,
# response_generator, and enrichment trace emission.
CATEGORY_LABELS = {
    "comparative_context": "Comparative Context",
    "temporal_trend": "Temporal Trend",
    "root_cause": "Root-Cause Analysis",
    "segmentation": "Segmentation",
}


# ── Analyst result collection ─────────────────────────────────────────────


@dataclass
class AnalystCollector:
    """Mutable collector for analyst loop output.

    Processes streamed ``ChatChunk`` objects and accumulates the key pieces
    (SQL, rows, answer) needed by downstream orchestration phases.
    """

    sql: str = ""
    rows: list[dict] = field(default_factory=list)
    answer: str = ""
    had_error: bool = False
    t0: float = field(default_factory=time.time)

    @property
    def duration_ms(self) -> int:
        return int((time.time() - self.t0) * 1000)

    def to_original_result(self) -> OriginalAnalystResult:
        return OriginalAnalystResult(
            sql=self.sql,
            rows=self.rows,
            answer=self.answer,
            duration_ms=self.duration_ms,
        )

    def process_chunk(self, chunk: ChatChunk) -> None:
        """Update collector state from a single analyst chunk."""
        if chunk.type == "sql" and chunk.sql:
            self.sql = chunk.sql
        elif chunk.type == "tool_result" and chunk.data:
            tool_name = chunk.data.get("tool", "")
            if tool_name == "run_sql" and chunk.data.get("result"):
                try:
                    parsed = json.loads(chunk.data["result"])
                    rows = parsed.get("rows", [])
                    if rows:
                        self.rows = rows
                except (json.JSONDecodeError, AttributeError):
                    pass
        elif chunk.type == "answer" and chunk.content:
            self.answer = chunk.content
        elif chunk.type in ("error", "clarification"):
            self.had_error = True


# ── DAG callback builders ─────────────────────────────────────────────────


def build_dag_callbacks(
    agent_name: str,
    conversation_id: str,
) -> tuple[list[ChatChunk], Callable[[SubTask], Awaitable[None]], Callable[[SubTask], Awaitable[None]]]:
    """Build on_task_start and on_task_complete callbacks for DAG execution.

    Returns (pending_chunks, on_task_start, on_task_complete).  The callbacks
    append chunks to ``pending_chunks``; the caller yields them after DAG completes.
    """
    pending_chunks: list[ChatChunk] = []

    async def on_task_start(task: SubTask) -> None:
        pending_chunks.append(ChatChunk(
            type="status",
            content=f"[{task.id}] Running {task.agent}: {task.task[:80]}...",
            data={"agent": agent_name, "task_id": task.id, "phase": "task_running"},
            conversation_id=conversation_id,
            timestamp=time.time(),
        ))

    async def on_task_complete(task: SubTask) -> None:
        result = task.result
        pending_chunks.append(ChatChunk(
            type="agent_trace",
            data={
                "task_id": task.id,
                "agent": task.agent,
                "category": task.category,
                "task": task.task,
                "depends_on": task.depends_on,
                "final_sql": result.sql if result else None,
                "final_answer": result.answer if result else None,
                "success": result.success if result else False,
                "error": result.error if result else None,
                "duration_ms": result.duration_ms if result else None,
                "steps": result.trace_steps if result else None,
            },
            content=f"[{task.id}] {task.agent} {'completed' if task.status == 'done' else task.status}",
            conversation_id=conversation_id,
            timestamp=time.time(),
        ))

    return pending_chunks, on_task_start, on_task_complete


# ── Enrichment trace emission ─────────────────────────────────────────────


async def yield_enrichment_traces(
    question: str,
    analyst_sql: str,
    analyst_answer: str,
    analyst_duration_ms: int,
    plan: OrchestratorPlan,
    results: dict[str, SubTaskResult],
    conversation_id: str,
) -> AsyncGenerator[ChatChunk, None]:
    """Yield enrichment_trace chunks for the citation system.

    Source [1] = original analyst; additional tasks start at [2].
    """
    yield ChatChunk(
        type="enrichment_trace",
        data={
            "source_index": 1,
            "category": "SQL Analysis",
            "question": question,
            "rationale": "Original analyst answer",
            "final_sql": analyst_sql,
            "final_answer": analyst_answer,
            "success": True,
            "duration_ms": analyst_duration_ms,
            "steps": [],
        },
        conversation_id=conversation_id,
        timestamp=time.time(),
    )
    await asyncio.sleep(0)

    for i, task in enumerate(plan.tasks, start=2):
        result = results.get(task.id)
        if not result or not result.success:
            continue
        category_label = CATEGORY_LABELS.get(task.category, task.agent.replace("_", " ").title())
        yield ChatChunk(
            type="enrichment_trace",
            data={
                "source_index": i,
                "category": category_label,
                "question": task.task,
                "rationale": plan.reasoning,
                "final_sql": result.sql,
                "final_answer": result.answer,
                "success": True,
                "duration_ms": result.duration_ms,
                "steps": result.trace_steps or [],
            },
            conversation_id=conversation_id,
            timestamp=time.time(),
        )
        await asyncio.sleep(0)


# ── Evidence block building ───────────────────────────────────────────────


def build_evidence_blocks(
    question: str,
    plan: OrchestratorPlan,
    results: dict[str, SubTaskResult],
    original: OriginalAnalystResult | None = None,
) -> str:
    """Build formatted evidence text from all sources for synthesis prompts.

    When *original* is provided it becomes Source [1] and enrichment tasks
    start at [2].  Returns the joined evidence string.
    """
    evidence_entries: list[str] = []
    source_offset = 0

    if original:
        source_offset = 1
        rows_summary = summarize_results(original.rows, max_rows=10)
        evidence_entries.append(
            f"### Source [1]: Original Analysis\n"
            f"**Task:** {question}\n"
            f"**SQL:** `{original.sql or '(none)'}`\n"
            f"**Results ({len(original.rows)} rows):** {rows_summary}\n"
            f"**Answer:** {original.answer}"
        )

    task_id_to_index = {
        task.id: i + source_offset
        for i, task in enumerate(plan.tasks, start=1)
    }

    for task in plan.tasks:
        result = results.get(task.id)
        if not result:
            continue

        idx = task_id_to_index[task.id]
        label = CATEGORY_LABELS.get(task.category, task.agent.replace("_", " ").title())

        if not result.success:
            evidence_entries.append(
                f"### Source [{idx}]: {label}\n"
                f"**Task:** {task.task}\n"
                f"**Status:** Failed — {result.error or 'no data available'}"
            )
            continue

        rows_summary = summarize_results(result.rows, max_rows=10)
        evidence_entries.append(
            f"### Source [{idx}]: {label}\n"
            f"**Task:** {task.task}\n"
            f"**SQL:** `{result.sql or '(none)'}`\n"
            f"**Results ({len(result.rows)} rows):** {rows_summary}\n"
            f"**Answer:** {result.answer}"
        )

    return "\n\n".join(evidence_entries) if evidence_entries else "(no evidence available)"


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
    tools_executed = False

    for iteration in range(max_iter):
        logger.info("--- %s iteration %d/%d ---", agent_name.title(), iteration + 1, max_iter)

        llm_start = time.time()
        try:
            response = await llm.chat(
                messages,
                tools=tool_registry.get_schemas(),
                force_tool_use=not tools_executed,
            )
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

                tools_executed = True

                yield ChatChunk(
                    type="tool_result",
                    data={"agent": agent_name, "tool": tc.name, "result": result},
                    tool_name=tc.name,
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)
        else:
            # Guard rail: force at least one tool call before accepting a
            # text-only answer.  Gives the LLM exactly one retry.
            if not tools_executed:
                logger.warning(
                    "%s returned text without calling tools (iter %d), injecting corrective message",
                    agent_name, iteration + 1,
                )
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append({
                    "role": "user",
                    "content": (
                        "You MUST call one of your available tools before answering. "
                        "The data is available in the tool context. "
                        "Choose the most appropriate analysis tool for the task."
                    ),
                })
                continue

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
