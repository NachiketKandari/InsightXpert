"""Orchestrator agent — routes through analyst -> statistician pipeline."""

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
        "analyst"      — analyst only (original behaviour)
        "auto"         — analyst, then statistician if results are available
        "statistician" — analyst, then statistician (same as auto)
    """
    # --- Phase 1: Analyst ---
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
        # Capture SQL and results from tool_result chunks
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
                except (json.JSONDecodeError, AttributeError):
                    pass

        yield chunk

    # --- Phase 2: Statistician (conditional) ---
    if agent_mode == "analyst":
        return

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
