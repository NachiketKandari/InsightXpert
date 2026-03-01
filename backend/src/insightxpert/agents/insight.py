"""Insight enrichment agent -- automatic depth expansion for analyst answers.

Implements a three-step enrichment pipeline:

1. **Plan** -- A single LLM call examines the analyst's answer and identifies
   1-3 investigative sub-queries (comparative, temporal, root-cause, segmentation).
2. **Execute** -- Each sub-query is run through the existing ``analyst_loop``
   in parallel via ``asyncio.Task``.
3. **Synthesize** -- A single LLM call combines all evidence into a
   leadership-grade insight response.

The pipeline degrades gracefully at every level: if any step fails, the
analyst's original answer stands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator

from insightxpert.agents.analyst import analyst_loop
from insightxpert.agents.common import summarize_results
from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt
from insightxpert.rag.store import VectorStore
from insightxpert.training.documentation import DOCUMENTATION
from insightxpert.training.schema import DDL

logger = logging.getLogger("insightxpert.insight")


@dataclass
class EnrichmentQuestion:
    category: str       # "comparative_context" | "temporal_trend" | "root_cause" | "segmentation"
    question: str       # Natural-language question for sub-analyst
    rationale: str      # Why this enrichment matters


@dataclass
class EnrichmentResult:
    category: str
    question: str
    sql: str
    rows: list[dict]
    answer: str
    success: bool
    error: str | None = None
    rationale: str = ""
    source_index: int = 0
    trace_steps: list[dict] | None = None
    duration_ms: int | None = None


async def plan_enrichment(
    question: str,
    analyst_answer: str,
    analyst_sql: str,
    analyst_results: list[dict],
    llm: LLMProvider,
    db: DatabaseConnector,
    ddl: str,
    documentation: str,
) -> list[EnrichmentQuestion]:
    """Plan 1-3 enrichment angles via a single LLM call.

    Returns an empty list on any failure -- the analyst answer stands alone.
    """
    results_summary = summarize_results(analyst_results)

    system_prompt = render_prompt(
        "insight_planner.j2",
        engine=db.engine,
        ddl=ddl,
        documentation=documentation,
        question=question,
        analyst_answer=analyst_answer,
        analyst_sql=analyst_sql,
        results_summary=results_summary,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Analyze the analyst's work and return enrichment questions as JSON."},
    ]

    try:
        response = await llm.chat(messages, tools=None)
        raw = (response.content or "").strip()

        # Strip markdown fencing if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)
        enrichments_raw = parsed.get("enrichments", [])

        enrichments = []
        for item in enrichments_raw[:3]:  # Cap at 3
            enrichments.append(EnrichmentQuestion(
                category=item.get("category", "comparative_context"),
                question=item["question"],
                rationale=item.get("rationale", ""),
            ))

        logger.info("Insight planner produced %d enrichment questions", len(enrichments))
        for i, eq in enumerate(enrichments):
            logger.info("  [%d] %s: %s", i, eq.category, eq.question[:80])

        return enrichments

    except Exception as exc:
        logger.warning("Insight planner failed, skipping enrichment: %s", exc, exc_info=True)
        return []


async def _drain_sub_analyst(
    enrichment: EnrichmentQuestion,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str,
    ddl: str,
    documentation: str,
) -> EnrichmentResult:
    """Run analyst_loop for one enrichment question and collect results silently."""
    collected_sql = ""
    collected_rows: list[dict] = []
    collected_answer = ""
    trace_steps: list[dict] = []
    t0 = time.time()

    try:
        async for chunk in analyst_loop(
            question=enrichment.question,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=conversation_id,
            history=None,
            ddl_override=ddl,
            documentation_override=documentation,
            clarification_enabled=False,
        ):
            step: dict = {
                "type": chunk.type,
                "timestamp": chunk.timestamp or time.time(),
            }

            if chunk.type == "tool_call" and chunk.data:
                step["tool_name"] = chunk.data.get("tool", "")
                step["tool_args"] = chunk.data.get("args", {})
                step["llm_reasoning"] = chunk.data.get("llm_reasoning", "")
                if chunk.sql:
                    step["sql"] = chunk.sql
            elif chunk.type == "sql" and chunk.sql:
                step["sql"] = chunk.sql
                collected_sql = chunk.sql
            elif chunk.type == "tool_result" and chunk.data:
                tool_name = chunk.data.get("tool", "")
                step["tool_name"] = tool_name
                result_str = str(chunk.data.get("result", ""))
                step["result_preview"] = result_str[:500]
                step["result_data"] = result_str
                if tool_name == "run_sql" and chunk.data.get("result"):
                    try:
                        parsed = json.loads(chunk.data["result"])
                        rows = parsed.get("rows", [])
                        if rows:
                            collected_rows = rows
                    except (json.JSONDecodeError, AttributeError):
                        pass
            elif chunk.type == "answer" and chunk.content:
                step["content"] = chunk.content
                collected_answer = chunk.content
            elif chunk.type == "error" and chunk.content:
                step["content"] = chunk.content
            else:
                if chunk.content:
                    step["content"] = chunk.content

            trace_steps.append(step)

        duration_ms = int((time.time() - t0) * 1000)

        return EnrichmentResult(
            category=enrichment.category,
            question=enrichment.question,
            sql=collected_sql,
            rows=collected_rows,
            answer=collected_answer,
            success=bool(collected_answer),
            rationale=enrichment.rationale,
            trace_steps=trace_steps,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        logger.warning("Sub-analyst failed for '%s': %s", enrichment.question[:60], exc)
        return EnrichmentResult(
            category=enrichment.category,
            question=enrichment.question,
            sql="",
            rows=[],
            answer="",
            success=False,
            error=str(exc),
            rationale=enrichment.rationale,
            trace_steps=trace_steps,
            duration_ms=duration_ms,
        )


async def execute_enrichments(
    enrichments: list[EnrichmentQuestion],
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str,
    ddl: str,
    documentation: str,
) -> AsyncGenerator[ChatChunk | EnrichmentResult, None]:
    """Execute enrichment sub-queries in parallel, yielding status chunks and results."""
    cid = conversation_id

    tasks = [
        asyncio.create_task(
            _drain_sub_analyst(eq, llm, db, rag, config, cid, ddl, documentation),
            name=f"enrichment-{eq.category}",
        )
        for eq in enrichments
    ]

    completed = 0
    total = len(tasks)

    for coro in asyncio.as_completed(tasks):
        result = await coro
        completed += 1

        status_label = (
            f"Enrichment {completed}/{total} complete: {result.category.replace('_', ' ')}"
            if result.success
            else f"Enrichment {completed}/{total}: {result.category.replace('_', ' ')} (no data)"
        )
        yield ChatChunk(
            type="status",
            content=status_label,
            data={"agent": "insight"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        yield result


async def synthesize_insight(
    question: str,
    analyst_answer: str,
    analyst_sql: str,
    analyst_results: list[dict],
    enrichment_results: list[EnrichmentResult],
    llm: LLMProvider,
    db: DatabaseConnector,
    ddl: str,
    documentation: str,
) -> str:
    """Synthesize all evidence into a leadership-grade insight via one LLM call."""
    results_summary = summarize_results(analyst_results)

    # Build enrichment data block with source numbers for citation
    enrichment_entries = []
    for er in enrichment_results:
        if not er.success:
            enrichment_entries.append(
                f"### {er.category.replace('_', ' ').title()}\n"
                f"**Question:** {er.question}\n"
                f"**Status:** Failed -- no data available."
            )
            continue

        er_summary = summarize_results(er.rows, max_rows=10)
        label = f"Source [{er.source_index}]: " if er.source_index else ""
        enrichment_entries.append(
            f"### {label}{er.category.replace('_', ' ').title()}\n"
            f"**Question:** {er.question}\n"
            f"**SQL:** `{er.sql}`\n"
            f"**Results:** {er_summary}\n"
            f"**Sub-analyst answer:** {er.answer}"
        )

    enrichment_data = "\n\n".join(enrichment_entries) if enrichment_entries else "(no enrichment data)"

    system_prompt = render_prompt(
        "insight_synthesizer.j2",
        engine=db.engine,
        ddl=ddl,
        documentation=documentation,
        question=question,
        analyst_answer=analyst_answer,
        analyst_sql=analyst_sql,
        results_summary=results_summary,
        enrichment_data=enrichment_data,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Synthesize all the evidence into a leadership-grade insight response."},
    ]

    try:
        response = await llm.chat(messages, tools=None)
        return response.content or "Unable to synthesize insight."
    except Exception as exc:
        logger.error("Insight synthesis failed: %s", exc, exc_info=True)
        return f"Insight synthesis encountered an error: {exc}"


async def insight_enrichment_phase(
    question: str,
    analyst_answer: str,
    analyst_sql: str,
    analyst_results: list[dict],
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str,
    ddl_override: str | None = None,
    docs_override: str | None = None,
) -> AsyncGenerator[ChatChunk, None]:
    """Top-level entry point for the insight enrichment pipeline.

    Orchestrates: plan -> execute -> synthesize.
    Yields status chunks for progress and a final "insight" chunk.
    """
    cid = conversation_id
    ddl = ddl_override or DDL
    docs = docs_override or DOCUMENTATION

    yield ChatChunk(
        type="status",
        content="Planning enrichment angles...",
        data={"agent": "insight"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    enrichments = await plan_enrichment(
        question=question,
        analyst_answer=analyst_answer,
        analyst_sql=analyst_sql,
        analyst_results=analyst_results,
        llm=llm,
        db=db,
        ddl=ddl,
        documentation=docs,
    )

    if not enrichments:
        logger.info("No enrichments planned; analyst answer stands alone.")
        return

    yield ChatChunk(
        type="status",
        content=f"Investigating {len(enrichments)} enrichment angle{'s' if len(enrichments) > 1 else ''}...",
        data={"agent": "insight"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    enrichment_results: list[EnrichmentResult] = []
    async for item in execute_enrichments(
        enrichments, llm, db, rag, config, cid, ddl, docs,
    ):
        if isinstance(item, ChatChunk):
            yield item
        elif isinstance(item, EnrichmentResult):
            enrichment_results.append(item)

    # Re-order results to match original enrichment planning order
    # (asyncio.as_completed returns in non-deterministic order)
    result_map = {(er.category, er.question): er for er in enrichment_results}
    ordered_results = [result_map[(eq.category, eq.question)] for eq in enrichments if (eq.category, eq.question) in result_map]

    # Assign 1-based source indices and yield enrichment_trace chunks
    source_idx = 0
    for er in ordered_results:
        if er.success:
            source_idx += 1
            er.source_index = source_idx
            yield ChatChunk(
                type="enrichment_trace",
                data={
                    "source_index": source_idx,
                    "category": er.category,
                    "question": er.question,
                    "rationale": er.rationale,
                    "final_sql": er.sql,
                    "final_answer": er.answer,
                    "success": True,
                    "duration_ms": er.duration_ms,
                    "steps": er.trace_steps,
                },
                conversation_id=cid,
                timestamp=time.time(),
            )

    successful = [er for er in ordered_results if er.success]
    if not successful:
        logger.warning("All enrichments failed; analyst answer stands alone.")
        yield ChatChunk(
            type="status",
            content="Enrichment investigations returned no data. Analyst answer stands.",
            data={"agent": "insight"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        return

    yield ChatChunk(
        type="status",
        content="Synthesizing enriched insight...",
        data={"agent": "insight"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    synthesized = await synthesize_insight(
        question=question,
        analyst_answer=analyst_answer,
        analyst_sql=analyst_sql,
        analyst_results=analyst_results,
        enrichment_results=ordered_results,
        llm=llm,
        db=db,
        ddl=ddl,
        documentation=docs,
    )

    yield ChatChunk(
        type="insight",
        content=synthesized,
        data={"agent": "insight"},
        conversation_id=cid,
        timestamp=time.time(),
    )
