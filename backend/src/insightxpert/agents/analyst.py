"""Analyst agent -- the core text-to-SQL pipeline.

Implements a 5-step agentic loop that converts a natural-language question
into an evidence-backed answer:

1. **RAG retrieval** -- Searches the vector store for similar past Q&A pairs
   and anomaly findings to provide few-shot context to the LLM.
2. **Prompt assembly** -- Renders the ``analyst_system.j2`` template with DDL,
   business documentation, and RAG hits, then builds the full message list
   (system prompt -> conversation history -> user question).
3. **Agentic loop** -- Iteratively calls the LLM, which may invoke tools
   (``run_sql``, ``get_schema``, ``search_similar``).  Tool results are
   appended back into the conversation and the LLM is called again until it
   produces a final text answer or the iteration limit is reached.
4. **Guard rail** -- On the first iteration, if the LLM responds without
   calling any tool, the response is rejected and the LLM is forced to
   execute a SQL query before answering.  This prevents hallucinated answers
   that bypass the database.
5. **Auto-save** -- When the loop completes successfully, the question + SQL
   pair is persisted into the RAG store, creating a self-improving feedback
   loop where future similar questions benefit from past successful queries.
"""

from __future__ import annotations

import asyncio
import json
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


def _extract_sql_from_messages(messages: list[dict]) -> str | None:
    """Extract the last SQL query from the conversation message history.

    Walks the message list in **reverse** (most-recent-first) looking for SQL
    in two places:

    1. A ``run_sql`` tool call on an assistant message -- the ``sql`` argument
       is returned directly.
    2. A fenced SQL code block (````sql ... `````) in any message's text
       content -- the first regex match is returned.

    This is used after the agentic loop finishes to find the SQL that produced
    the answer, so it can be saved as a Q&A pair in the RAG store.

    Args:
        messages: The full conversation message list (system + history + user
            + assistant/tool rounds).

    Returns:
        The SQL string if found, or ``None`` if no SQL was produced.
    """
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
    ddl_override: str | None = None,
    documentation_override: str | None = None,
    stats_context: str | None = None,
    stats_groups: list[str] | None = None,
    clarification_enabled: bool = False,
    rag_retrieval: bool = True,
) -> AsyncGenerator[ChatChunk, None]:
    """Run the analyst agentic loop for a single user question.

    This is an **async generator** that yields ``ChatChunk`` objects as the
    pipeline progresses.  The caller (typically the orchestrator or SSE
    endpoint) iterates over the chunks and streams them to the frontend.

    Yielded ChatChunk types (in typical order):
        - ``"status"``      -- progress updates for the UI status bar
        - ``"tool_call"``   -- notification that a tool is being invoked
        - ``"sql"``         -- the SQL query text (for display)
        - ``"tool_result"`` -- raw result from tool execution
        - ``"answer"``      -- the LLM's final natural-language answer
        - ``"error"``       -- on LLM failure or iteration exhaustion

    Args:
        question: The user's natural-language question.
        llm: LLM provider implementing the ``chat()`` protocol.
        db: Database connector for SQL execution.
        rag: Vector store for RAG retrieval and auto-save.
        config: Application settings (iteration limits, row limits, etc.).
        conversation_id: Optional ID for multi-turn conversation tracking.
        history: Optional list of prior conversation messages for multi-turn
            context.  These are injected between the system prompt and the
            current user question.
        tool_registry: Optional custom tool registry; defaults to the
            standard analyst toolset (``run_sql``, ``get_schema``,
            ``search_similar``).

    Yields:
        ChatChunk instances representing each stage of the pipeline.
    """
    cid = conversation_id or ""
    loop_start = time.time()

    # Build tool registry and context
    if tool_registry is None:
        tool_registry = default_registry(clarification_enabled=clarification_enabled)
    tool_context = ToolContext(db=db, rag=rag, row_limit=config.sql_row_limit)

    logger.info("=" * 60)
    logger.info("NEW QUESTION [%s]: %s", cid, question)
    logger.info("=" * 60)

    yield ChatChunk(
        type="status",
        content="Searching knowledge base for context...",
        data={"agent": "analyst"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    # -- Step 1: RAG retrieval --
    # Retrieve up to 3 similar Q&A pairs that are close enough (distance <= 1.0)
    # and whose SQL was previously validated. Capped at 3 to keep context tight.
    # Skipped entirely when rag_retrieval=False (admin toggle).
    similar_qa: list[dict] = []
    if rag_retrieval:
        rag_start = time.time()
        similar_qa = await asyncio.to_thread(
            rag.search_qa, question, n=3, max_distance=1.0, sql_valid_only=True,
        )
        rag_ms = (time.time() - rag_start) * 1000

        logger.info(
            "RAG retrieval (%.0fms): qa=%d (threshold=1.0, valid-only)",
            rag_ms, len(similar_qa),
        )
        if similar_qa:
            for i, qa in enumerate(similar_qa):
                logger.debug("  qa[%d] dist=%.3f: %s", i, qa["distance"], qa["document"][:100])
    else:
        logger.info("RAG retrieval skipped (rag_retrieval=False)")

    # Collect titles for frontend dropdown display
    rag_titles: list[str] = []
    for qa in similar_qa:
        q = qa.get("metadata", {}).get("question", "")
        rag_titles.append(q or qa.get("document", "")[:80])

    yield ChatChunk(
        type="status",
        content=f"Found {len(similar_qa)} similar queries. Analyzing with AI...",
        data={"rag_context": rag_titles} if rag_titles else None,
        conversation_id=cid,
        timestamp=time.time(),
    )
    await asyncio.sleep(0)

    # -- Step 2: System prompt assembly --
    # Use overrides from the active dataset if provided, else fall back to
    # the hardcoded training files.
    active_ddl = ddl_override or DDL
    active_docs = documentation_override or DOCUMENTATION

    system_prompt = render_prompt(
        "analyst_system.j2",
        engine=db.engine,
        ddl=active_ddl,
        documentation=active_docs,
        similar_qa=similar_qa,
        relevant_findings=[],
        stats_context=stats_context,
        clarification_enabled=clarification_enabled,
    )

    # Fallback: if the DB-sourced template predates the stats_context feature
    # it won't have the {% if stats_context %} block, so inject directly.
    if stats_context and "Pre-Computed Dataset Statistics" not in system_prompt:
        system_prompt = (
            system_prompt
            + "\n\n## Pre-Computed Dataset Statistics (use these before running SQL if sufficient)\n\n"
            + stats_context
            + "\n\nIf the answer can be derived directly from the statistics above, you may answer"
            " without running a SQL query. If you need finer-grained data (filters, sub-segments,"
            " time slices beyond what's shown), use run_sql as normal."
        )

    # -- Step 3: Message list assembly --
    # The ordering matters for LLM context:
    #   1. System prompt -- sets the persona, schema, rules, and RAG context
    #   2. Conversation history -- prior user/assistant turns for multi-turn
    #   3. Current user question -- the new query to answer
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    # Inject conversation history for multi-turn context
    if history:
        messages.extend(history)
        logger.info("Injected %d history messages for conversation %s", len(history), cid)

    messages.append({"role": "user", "content": question})

    max_iter = config.max_agent_iterations

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

        # -- Step 4: Guard rail -- "force tool use" on first iteration --
        # If the LLM produces a text-only response without ever having
        # executed a tool in this session, we reject it and inject a
        # corrective user message demanding a run_sql call.  This prevents
        # the LLM from hallucinating answers based on its training data or
        # the few-shot examples in the prompt instead of querying the
        # actual database.  Once any tool has been executed (tools_executed
        # becomes True), subsequent text-only responses are accepted as the
        # final answer.
        # Exception: when pre-computed stats context was injected, the LLM
        # is permitted to answer directly from those stats without SQL.
        if not response.tool_calls and not tools_executed:
            if stats_context:
                logger.info(
                    "LLM answered without tool calls on iteration %d — permitted (stats_context provided)",
                    iteration + 1,
                )
                # Emit stats context chunk for frontend transparency
                yield ChatChunk(
                    type="stats_context",
                    content=stats_context,
                    data={"groups": stats_groups or []},
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                # Fall through to the final-answer branch below
            else:
                logger.warning(
                    "LLM answered without tool calls on iteration %d — forcing tool use",
                    iteration + 1,
                )
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                })
                force_msg = (
                    "You MUST use a tool before answering. "
                    "Use run_sql to query the database, or use clarify if the "
                    "question is ambiguous. Do not answer from memory or prior context."
                ) if clarification_enabled else (
                    "You MUST use the run_sql tool to query the database before "
                    "answering. Do not answer from memory or prior context. "
                    "Please write and execute a SQL query now."
                )
                messages.append({
                    "role": "user",
                    "content": force_msg,
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

                # Handle clarification tool — emit clarification chunk and stop
                if tc.name == "clarify":
                    try:
                        clarify_data = json.loads(result)
                    except (json.JSONDecodeError, TypeError):
                        clarify_data = {"clarification": result}
                    yield ChatChunk(
                        type="clarification",
                        content=clarify_data.get("clarification", ""),
                        data={"skip_allowed": True},
                        conversation_id=cid,
                        timestamp=time.time(),
                    )
                    return

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                })

                tool_result_data = {"tool": tc.name, "result": result}
                if tc.name == "run_sql":
                    if tc.arguments.get("visualization"):
                        tool_result_data["visualization"] = tc.arguments["visualization"]
                    if tc.arguments.get("x_column"):
                        tool_result_data["x_column"] = tc.arguments["x_column"]
                    if tc.arguments.get("y_column"):
                        tool_result_data["y_column"] = tc.arguments["y_column"]

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

            # -- Step 5: Auto-save -- self-improving feedback loop --
            # After a successful answer, extract the SQL that was executed
            # and save the (question, sql) pair back to the RAG store with
            # sql_valid=True.  On future questions, this pair will surface
            # as a few-shot example, improving the LLM's SQL accuracy over
            # time.  This creates a flywheel effect: more usage -> more
            # saved examples -> better future answers.
            sql = _extract_sql_from_messages(messages)
            if sql:
                try:
                    await asyncio.to_thread(
                        rag.add_qa_pair, question, sql, {"sql_valid": True},
                    )
                    logger.debug("Auto-saved QA pair to RAG (sql_valid=True)")
                except Exception:
                    logger.debug("Auto-save QA pair to RAG failed", exc_info=True)
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
