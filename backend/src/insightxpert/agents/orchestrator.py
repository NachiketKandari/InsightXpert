"""Orchestrator agent -- two-phase pipeline: analyst then statistician.

Implements the top-level question-answering flow:

**Phase 1 (Analyst):** Always runs.  Converts the user's natural-language
question into SQL, executes it, and produces an evidence-backed answer.
While streaming analyst chunks to the caller, the orchestrator also
*intercepts* ``"sql"`` and ``"tool_result"`` chunks to capture the last
executed SQL statement and its result rows.

**Phase 2 (Statistician):** Conditionally runs.  If the analyst produced
non-empty query results *and* the ``agent_mode`` is not ``"analyst"``,
the captured SQL and result rows are forwarded to the statistician agent
for deeper statistical analysis (e.g. trends, outliers, correlations).

The ``agent_mode`` parameter controls gating:
    - ``"analyst"``      -- Phase 1 only; statistician is always skipped.
    - ``"auto"``         -- Phase 1, then Phase 2 only if analyst returned
                            non-empty result rows.
    - ``"statistician"`` -- Same behaviour as ``"auto"``.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from insightxpert.agents.analyst import analyst_loop
from insightxpert.agents.statistician import statistician_loop
from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.rag.store import VectorStore

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
) -> AsyncGenerator[ChatChunk, None]:
    """Run the analyst -> statistician pipeline.

    agent_mode:
        "analyst"      -- analyst only (original behaviour)
        "auto"         -- analyst, then statistician if results are available
        "statistician" -- analyst, then statistician (same as auto)
    """
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

    # --- Phase 2: Statistician (conditional) ---
    # Skip Phase 2 entirely if agent_mode is "analyst" (user or config
    # explicitly requested analyst-only mode).
    if agent_mode == "analyst":
        return

    # Skip Phase 2 if the analyst produced no usable result rows.
    # This happens when the query returned zero rows, the LLM never
    # called run_sql, or the result couldn't be parsed.
    if not collected_results:
        logger.info("Orchestrator: no analyst results to pass to statistician, skipping")
        return

    cid = conversation_id or ""

    logger.info(
        "Orchestrator: passing %d rows to statistician (mode=%s)",
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
