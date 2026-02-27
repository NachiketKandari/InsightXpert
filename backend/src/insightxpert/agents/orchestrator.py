"""Orchestrator agent -- two-phase pipeline: analyst then downstream agent.

Implements the top-level question-answering flow:

**Phase 1 (Analyst):** Always runs.  Converts the user's natural-language
question into SQL, executes it, and produces an evidence-backed answer.
While streaming analyst chunks to the caller, the orchestrator also
*intercepts* ``"sql"`` and ``"tool_result"`` chunks to capture the last
executed SQL statement and its result rows.

**Phase 2 (Downstream agent):** Conditionally runs.  If the analyst produced
non-empty query results *and* the ``agent_mode`` is not ``"analyst"``,
the captured SQL and result rows are forwarded to the downstream agent.

The ``agent_mode`` parameter controls routing:
    - ``"analyst"``      -- Phase 1 only; no downstream agent.
    - ``"auto"``         -- Phase 1, then statistician (if results available).
    - ``"statistician"`` -- Same behaviour as ``"auto"``.
    - ``"advanced"``     -- Phase 1, then advanced analytics agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from insightxpert.agents.advanced_agent import advanced_analytics_loop
from insightxpert.agents.analyst import analyst_loop
from insightxpert.agents.statistician import statistician_loop
from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.rag.store import VectorStore
from insightxpert.training.documentation import DOCUMENTATION
from insightxpert.training.schema import DDL

logger = logging.getLogger("insightxpert.orchestrator")


async def orchestrator_loop(
    question: str,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str | None = None,
    history: list[dict] | None = None,
    agent_mode: str = "auto",
    dataset_service=None,
    skip_clarification: bool = False,
) -> AsyncGenerator[ChatChunk, None]:
    """Run the analyst -> downstream agent pipeline.

    agent_mode:
        "analyst"      -- analyst only (no downstream agent)
        "auto"         -- analyst, then statistician if results are available
        "statistician" -- analyst, then statistician (same as auto)
        "advanced"     -- analyst, then advanced analytics agent
    """
    # Resolve active dataset DDL and documentation
    ddl_override: str | None = None
    docs_override: str | None = None

    if dataset_service is not None:
        active_ds = await asyncio.to_thread(dataset_service.get_active_dataset)
        if active_ds:
            ddl_override = active_ds.get("ddl")
            docs_override = await asyncio.to_thread(
                dataset_service.build_documentation_markdown, active_ds["id"],
            )

    # --- Clarification pre-check ---
    if not skip_clarification:
        from insightxpert.agents.clarifier import clarification_check

        # Emit an immediate status chunk so the browser receives the first SSE
        # event right away and the "Thinking…" spinner is replaced before the
        # (slow) clarification LLM call starts.
        yield ChatChunk(
            type="status",
            content="Analyzing your question...",
            conversation_id=conversation_id or "",
            timestamp=time.time(),
        )

        clarify_ddl = ddl_override or DDL
        clarify_docs = docs_override or DOCUMENTATION
        try:
            result = await clarification_check(
                question=question,
                ddl=clarify_ddl,
                documentation=clarify_docs,
                llm=llm,
                history=history,
            )
            if result.action == "clarify" and result.question:
                yield ChatChunk(
                    type="clarification",
                    content=result.question,
                    data={"skip_allowed": True},
                    conversation_id=conversation_id or "",
                    timestamp=time.time(),
                )
                return
        except Exception as e:
            logger.warning("Clarification check failed, proceeding: %s", e)

    # --- Stats context pre-fetch ---
    stats_context: str | None = None
    if config.enable_stats_context:
        from insightxpert.agents.stats_resolver import StatsResolver
        try:
            stats_context = StatsResolver().resolve(question, db.engine)
        except Exception as _stats_err:
            logger.debug("StatsResolver failed, continuing without stats context: %s", _stats_err)

    # --- Phase 1: Analyst ---
    # collected_sql holds the *last* SQL statement executed by the analyst.
    # collected_results holds the parsed row dicts from the last run_sql
    # tool result.  Both are captured by intercepting streamed chunks so
    # they can be forwarded to the statistician in Phase 2.
    collected_sql: str = ""
    collected_results: list[dict] = []

    async for chunk in analyst_loop(
        question=question,
        llm=llm,
        db=db,
        rag=rag,
        config=config,
        conversation_id=conversation_id,
        history=history,
        ddl_override=ddl_override,
        documentation_override=docs_override,
        stats_context=stats_context,
    ):
        # Intercept SQL and result chunks for Phase 2 hand-off.
        # We keep the *last* SQL and result set because the analyst may
        # refine its query across multiple iterations.
        if chunk.type == "sql" and chunk.sql:
            collected_sql = chunk.sql

        if chunk.type == "tool_result" and chunk.data:
            tool_name = chunk.data.get("tool")
            raw = chunk.data.get("result", "")
            if tool_name == "run_sql" and raw:
                try:
                    parsed = json.loads(raw)
                    rows = parsed.get("rows", [])
                    if rows:
                        collected_results = rows
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.debug("Failed to parse run_sql result: %s", e)

        yield chunk

    # --- Phase 2 / Phase 3 (conditional) ---
    if agent_mode == "analyst":
        return

    if not collected_results:
        logger.info("Orchestrator: analyst returned no rows; skipping downstream phases")
        return

    cid = conversation_id or ""

    if agent_mode == "advanced":
        logger.info(
            "Orchestrator: routing %d rows to advanced analytics agent",
            len(collected_results),
        )
        async for chunk in advanced_analytics_loop(
            question=question,
            analyst_results=collected_results,
            analyst_sql=collected_sql,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=cid,
            ddl=ddl_override or DDL,
            documentation=docs_override or DOCUMENTATION,
        ):
            yield chunk
    else:
        # "auto" or "statistician"
        logger.info(
            "Orchestrator: routing %d rows to statistician (mode=%s)",
            len(collected_results), agent_mode,
        )
        async for chunk in statistician_loop(
            question=question,
            analyst_results=collected_results,
            analyst_sql=collected_sql,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=cid,
        ):
            yield chunk
