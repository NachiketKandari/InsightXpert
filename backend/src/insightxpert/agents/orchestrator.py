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
    - ``"agentic"``      -- Phase 1, then insight enrichment pipeline.
    - ``"auto"``         -- Phase 1, then statistician (if results available).
    - ``"statistician"`` -- Same behaviour as ``"auto"``.
    - ``"advanced"``     -- Phase 1, then advanced analytics agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from insightxpert.agents.advanced_agent import advanced_analytics_loop
from insightxpert.agents.analyst import analyst_loop
from insightxpert.agents.insight import insight_enrichment_phase
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
    stats_context_injection: bool = False,
    clarification_enabled: bool = False,
) -> AsyncGenerator[ChatChunk, None]:
    """Run the analyst -> downstream agent pipeline.

    agent_mode:
        "analyst"      -- analyst only (no downstream agent)
        "agentic"      -- analyst, then insight enrichment pipeline
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

    # Resolve effective clarification_enabled: if skip_clarification is True
    # (user clicked "Just answer"), disable clarification for this request.
    effective_clarification = clarification_enabled and not skip_clarification

    # --- Stats context pre-fetch ---
    stats_context: str | None = None
    stats_groups: list[str] = []
    if config.enable_stats_context and stats_context_injection:
        from insightxpert.agents.stats_resolver import StatsResolver
        try:
            stats_result = await asyncio.to_thread(StatsResolver().resolve, question, db.engine)
            if stats_result:
                stats_context = stats_result.markdown
                stats_groups = stats_result.groups
        except Exception as _stats_err:
            logger.debug("StatsResolver failed, continuing without stats context: %s", _stats_err)

    # --- Phase 1: Analyst ---
    # collected_sql holds the *last* SQL statement executed by the analyst.
    # collected_results holds the parsed row dicts from the last run_sql
    # tool result.  Both are captured by intercepting streamed chunks so
    # they can be forwarded to the statistician in Phase 2.
    collected_sql: str = ""
    collected_results: list[dict] = []
    collected_answer: str = ""

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
        stats_groups=stats_groups,
        clarification_enabled=effective_clarification,
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

        if chunk.type == "answer" and chunk.content:
            collected_answer = chunk.content

        yield chunk

    # --- Phase 2 / Phase 3 (conditional) ---
    if agent_mode == "analyst":
        return

    if not collected_results:
        logger.info("Orchestrator: analyst returned no rows; skipping downstream phases")
        return

    cid = conversation_id or ""

    if agent_mode == "agentic":
        if collected_answer:
            logger.info(
                "Orchestrator: routing to insight enrichment (answer=%d chars, %d rows)",
                len(collected_answer), len(collected_results),
            )
            async for chunk in insight_enrichment_phase(
                question=question,
                analyst_answer=collected_answer,
                analyst_sql=collected_sql,
                analyst_results=collected_results,
                llm=llm,
                db=db,
                rag=rag,
                config=config,
                conversation_id=cid,
                ddl_override=ddl_override,
                docs_override=docs_override,
            ):
                yield chunk
        else:
            logger.info("Orchestrator: agentic mode but no analyst answer; skipping enrichment")
    elif agent_mode == "advanced":
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
