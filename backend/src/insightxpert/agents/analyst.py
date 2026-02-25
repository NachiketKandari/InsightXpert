from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import AsyncGenerator

from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt
from insightxpert.rag.store import VectorStore
from insightxpert.training.documentation import DOCUMENTATION
from insightxpert.training.schema import DDL

from .tool_base import ToolContext, ToolRegistry
from .tools import default_registry

logger = logging.getLogger("insightxpert.analyst")

MAX_ITERATIONS = 10


def _extract_sql_from_messages(messages: list[dict]) -> str | None:
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                if tc.name == "run_sql":
                    return tc.arguments.get("sql")
        content = msg.get("content", "")
        if isinstance(content, str):
            match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                return match.group(1).strip()
    return None


async def analyst_loop(
    question: str,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str | None = None,
    history: list[dict] | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AsyncGenerator[ChatChunk, None]:
    cid = conversation_id or ""
    loop_start = time.time()

    # Build tool registry and context
    if tool_registry is None:
        tool_registry = default_registry()
    tool_context = ToolContext(db=db, rag=rag, row_limit=config.sql_row_limit)

    logger.info("=" * 60)
    logger.info("NEW QUESTION [%s]: %s", cid, question)
    logger.info("=" * 60)

    yield ChatChunk(
        type="status",
        content="Searching knowledge base for context...",
        conversation_id=cid,
        timestamp=time.time(),
    )

    rag_start = time.time()
    similar_qa = rag.search_qa(question, n=5, max_distance=1.0, sql_valid_only=True)
    relevant_findings = rag.search_findings(question, n=2)
    rag_ms = (time.time() - rag_start) * 1000

    logger.info(
        "RAG retrieval (%.0fms): qa=%d (threshold=1.0, valid-only) findings=%d",
        rag_ms, len(similar_qa), len(relevant_findings),
    )
    if similar_qa:
        for i, qa in enumerate(similar_qa):
            logger.debug("  qa[%d] dist=%.3f: %s", i, qa["distance"], qa["document"][:100])

    total_rag_hits = len(similar_qa) + len(relevant_findings)

    # Collect titles for frontend dropdown display
    rag_titles: list[str] = []
    for qa in similar_qa:
        q = qa.get("metadata", {}).get("question", "")
        rag_titles.append(q or qa.get("document", "")[:80])
    for finding in relevant_findings:
        rag_titles.append(f"Finding: {finding.get('document', '')[:60]}")

    yield ChatChunk(
        type="status",
        content=f"Found {total_rag_hits} similar queries. Analyzing with AI...",
        data={"rag_context": rag_titles} if rag_titles else None,
        conversation_id=cid,
        timestamp=time.time(),
    )
    await asyncio.sleep(0)

    system_prompt = render_prompt(
        "analyst_system.j2",
        ddl=DDL,
        documentation=DOCUMENTATION,
        similar_qa=similar_qa,
        relevant_findings=relevant_findings,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    # Inject conversation history for multi-turn context
    if history:
        messages.extend(history)
        logger.info("Injected %d history messages for conversation %s", len(history), cid)

    messages.append({"role": "user", "content": question})

    max_iter = config.max_agent_iterations or MAX_ITERATIONS

    tools_executed = False

    for iteration in range(max_iter):
        logger.info("--- Iteration %d/%d ---", iteration + 1, max_iter)

        llm_start = time.time()
        try:
            response = await llm.chat(messages, tools=tool_registry.get_schemas())
        except Exception as exc:
            logger.error("LLM call failed: %s", exc, exc_info=True)
            yield ChatChunk(
                type="error",
                content=f"LLM request failed: {exc}",
                conversation_id=cid,
                timestamp=time.time(),
            )
            return
        llm_ms = (time.time() - llm_start) * 1000

        # Guard: if the LLM tries to answer without ever executing a tool,
        # reject the response and force it to query the database first.
        if not response.tool_calls and not tools_executed:
            logger.warning(
                "LLM answered without tool calls on iteration %d — forcing tool use",
                iteration + 1,
            )
            messages.append({
                "role": "assistant",
                "content": response.content or "",
            })
            messages.append({
                "role": "user",
                "content": (
                    "You MUST use the run_sql tool to query the database before "
                    "answering. Do not answer from memory or prior context. "
                    "Please write and execute a SQL query now."
                ),
            })
            continue

        if response.tool_calls:
            tool_names = [tc.name for tc in response.tool_calls]
            logger.info("LLM response (%.0fms): tool_calls=%s", llm_ms, tool_names)
            if response.content:
                logger.debug("LLM thinking: %s", response.content[:200])

            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            })

            llm_reasoning = response.content or None

            for tc in response.tool_calls:
                yield ChatChunk(
                    type="tool_call",
                    content=f"Calling {tc.name}...",
                    sql=tc.arguments.get("sql") if tc.name == "run_sql" else None,
                    tool_name=tc.name,
                    args=tc.arguments,
                    data={"llm_reasoning": llm_reasoning} if llm_reasoning else None,
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)

                if tc.name == "run_sql" and tc.arguments.get("sql"):
                    logger.info("SQL: %s", tc.arguments["sql"])
                    yield ChatChunk(
                        type="sql",
                        sql=tc.arguments["sql"],
                        conversation_id=cid,
                        timestamp=time.time(),
                    )
                    await asyncio.sleep(0)

                    yield ChatChunk(
                        type="status",
                        content="Executing SQL query...",
                        conversation_id=cid,
                        timestamp=time.time(),
                    )
                    await asyncio.sleep(0)
                else:
                    yield ChatChunk(
                        type="status",
                        content=f"Running {tc.name}...",
                        conversation_id=cid,
                        timestamp=time.time(),
                    )
                    await asyncio.sleep(0)

                tool_start = time.time()
                result = await tool_registry.execute(
                    tc.name, tc.arguments, tool_context,
                )
                tool_ms = (time.time() - tool_start) * 1000
                tools_executed = True
                logger.info("Tool %s completed (%.0fms): %s", tc.name, tool_ms, result[:200])

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                })

                tool_result_data = {"tool": tc.name, "result": result}
                if tc.name == "run_sql" and tc.arguments.get("visualization"):
                    tool_result_data["visualization"] = tc.arguments["visualization"]

                yield ChatChunk(
                    type="tool_result",
                    data=tool_result_data,
                    tool_name=tc.name,
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)
        else:
            total_ms = (time.time() - loop_start) * 1000
            answer_preview = (response.content or "")[:200]
            logger.info("LLM final answer (%.0fms): %s...", llm_ms, answer_preview)
            logger.info(
                "DONE [%s] total=%.0fms iterations=%d",
                cid, total_ms, iteration + 1,
            )

            yield ChatChunk(
                type="answer",
                content=response.content,
                conversation_id=cid,
                timestamp=time.time(),
            )

            sql = _extract_sql_from_messages(messages)
            if sql:
                try:
                    rag.add_qa_pair(question, sql, {"sql_valid": True})
                    logger.debug("Auto-saved QA pair to RAG (sql_valid=True)")
                except Exception:
                    pass
            break
    else:
        total_ms = (time.time() - loop_start) * 1000
        logger.warning(
            "EXHAUSTED [%s] max iterations=%d total=%.0fms",
            cid, max_iter, total_ms,
        )
        yield ChatChunk(
            type="error",
            content=f"Agent reached maximum iterations ({max_iter}) without producing a final answer.",
            conversation_id=cid,
            timestamp=time.time(),
        )
