"""Deep Think agent -- 5W1H dimensional analysis pipeline.

Implements a six-phase flow:

1. **Dimension Extraction** — Single LLM call maps the question onto
   WHO/WHAT/WHEN/WHERE/HOW dimensions, derives WHY intent, and pre-plans
   targeted enrichment tasks for uncovered dimensions.

2. **Analyst** — Runs the existing ``analyst_loop`` unchanged so the user
   sees SQL + results + answer immediately.

3. **Targeted Enrichment** — Executes the pre-planned enrichment tasks from
   Phase 1 via DAG execution (reuses ``_run_sql_analyst`` and ``execute_dag``).

4. **Synthesis** — Combines all evidence into a 5W1H-structured insight with
   ``[[N]]`` citations using the ``deep_synthesizer.j2`` template.

5. **Auto-Investigation** — Evaluates the synthesis for analytical gaps and,
   if warranted, automatically executes follow-up SQL queries to fill them.

6. **Investigation Re-synthesis** — Integrates investigation findings into
   a final insight using ``investigation_synthesizer.j2``, focused on what
   changed rather than re-narrating prior evidence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from insightxpert.agents.analyst import analyst_loop
from insightxpert.agents.common import (
    CATEGORY_LABELS,
    AnalystCollector,
    build_dag_callbacks,
    build_evidence_blocks,
    yield_enrichment_traces,
)
from insightxpert.agents.dag_executor import (
    OrchestratorPlan,
    OriginalAnalystResult,
    SubTask,
    SubTaskResult,
    execute_dag,
)
from insightxpert.agents.response_generator import _fallback_answer
from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt
from insightxpert.rag.store import VectorStore

logger = logging.getLogger("insightxpert.deep_think")

_DIMENSION_TIMEOUT = 15
_SYNTHESIS_TIMEOUT = 60

_DIMENSION_LABELS = {
    "who": "WHO (Actors)",
    "what": "WHAT (Metrics)",
    "when": "WHEN (Temporal)",
    "where": "WHERE (Geographic)",
    "how": "HOW (Mechanisms)",
}


# ── Phase 1: Dimension Extraction ────────────────────────────────────────


async def _extract_dimensions(
    question: str,
    llm: LLMProvider,
    ddl: str,
    documentation: str,
    history: list[dict] | None = None,
) -> dict | None:
    """Extract 5W1H dimensions from the question via a single LLM call.

    Returns parsed JSON dict on success, or None on any failure.
    """
    system_prompt = render_prompt(
        "dimension_extractor.j2",
        ddl=ddl,
        documentation=documentation,
        question=question,
        history=history[-6:] if history else [],
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Analyze this question through the 5W1H dimensional framework."},
    ]

    t0 = time.time()
    try:
        response = await asyncio.wait_for(
            llm.chat(messages, tools=None),
            timeout=_DIMENSION_TIMEOUT,
        )
        raw = (response.content or "").strip()
        ms = int((time.time() - t0) * 1000)

        # Strip markdown fencing if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)
        logger.info(
            "Dimension extraction completed in %dms: %d enrichments suggested",
            ms,
            len(parsed.get("suggested_enrichments", [])),
        )
        return parsed

    except asyncio.TimeoutError:
        ms = int((time.time() - t0) * 1000)
        logger.warning("Dimension extraction timed out after %dms", ms)
        return None
    except Exception as exc:
        ms = int((time.time() - t0) * 1000)
        logger.warning("Dimension extraction failed (%dms): %s", ms, exc)
        return None


def _build_dimensions_context(dimensions: dict) -> str:
    """Format dimension analysis JSON into readable text for the synthesizer."""
    dims = dimensions.get("dimensions", {})
    lines: list[str] = []
    for key, label in _DIMENSION_LABELS.items():
        info = dims.get(key, {})
        status = info.get("status", "unknown")
        detail = info.get("detail", "")
        lines.append(f"- **{label}**: {status} — {detail}")
    return "\n".join(lines)


_VALID_AGENTS = {"sql_analyst", "quant_analyst"}


def _build_enrichment_plan(dimensions: dict) -> OrchestratorPlan | None:
    """Convert suggested_enrichments from dimension extraction into an OrchestratorPlan."""
    enrichments = dimensions.get("suggested_enrichments", [])
    if not enrichments:
        return None

    tasks: list[SubTask] = []
    seen_ids: set[str] = set()

    for item in enrichments[:3]:
        task_id = str(item.get("id", "")).upper()
        task_desc = str(item.get("task", ""))
        category = str(item.get("category", "")).lower()
        agent = str(item.get("agent", "sql_analyst"))
        depends_on = item.get("depends_on", [])

        if not task_id or not task_desc:
            continue

        if agent not in _VALID_AGENTS:
            agent = "sql_analyst"

        if category not in CATEGORY_LABELS:
            category = "comparative_context"

        if isinstance(depends_on, str):
            depends_on = [depends_on]
        depends_on = [str(d).upper() for d in depends_on if d]

        seen_ids.add(task_id)
        tasks.append(SubTask(
            id=task_id,
            agent=agent,
            task=task_desc,
            depends_on=depends_on,
            category=category,
        ))

    if not tasks:
        return None

    # Strip references to task IDs not in this plan
    for t in tasks:
        t.depends_on = [d for d in t.depends_on if d in seen_ids]

    # Quant analyst with no valid upstream dependencies can't operate — demote
    for t in tasks:
        if t.agent == "quant_analyst" and not t.depends_on:
            logger.warning("quant_analyst task %s has no dependencies; demoting to sql_analyst", t.id)
            t.agent = "sql_analyst"

    why_intent = dimensions.get("why_intent", "")
    return OrchestratorPlan(
        reasoning=f"5W1H dimensional analysis: {why_intent}",
        tasks=tasks,
    )


# ── Phase 4: Synthesis ───────────────────────────────────────────────────


async def _deep_synthesize(
    question: str,
    llm: LLMProvider,
    ddl: str,
    documentation: str,
    original: OriginalAnalystResult,
    plan: OrchestratorPlan,
    results: dict[str, SubTaskResult],
    dimensions: dict,
) -> str:
    """Build 5W1H-structured insight from all evidence via one LLM call."""
    evidence_data = build_evidence_blocks(question, plan, results, original)
    dimensions_summary = _build_dimensions_context(dimensions)
    why_intent = dimensions.get("why_intent", "Analytical exploration")

    system_prompt = render_prompt(
        "deep_synthesizer.j2",
        ddl=ddl,
        documentation=documentation,
        question=question,
        evidence_data=evidence_data,
        dimensions_summary=dimensions_summary,
        why_intent=why_intent,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Synthesize all evidence into a dimensionally-structured insight."},
    ]

    try:
        response = await asyncio.wait_for(
            llm.chat(messages, tools=None),
            timeout=_SYNTHESIS_TIMEOUT,
        )
        return response.content or _fallback_answer(plan, results, original)
    except Exception as exc:
        logger.error("Deep synthesis failed: %s", exc, exc_info=True)
        return _fallback_answer(plan, results, original)


# ── Phase 6: Investigation Re-synthesis ──────────────────────────────────


async def _investigation_synthesize(
    question: str,
    llm: LLMProvider,
    ddl: str,
    documentation: str,
    prior_synthesis: str,
    investigation_reasoning: str,
    prior_evidence: str,
    new_evidence: str,
) -> str:
    """Re-synthesize with investigation findings using a gap-focused prompt."""
    system_prompt = render_prompt(
        "investigation_synthesizer.j2",
        ddl=ddl,
        documentation=documentation,
        question=question,
        prior_synthesis=prior_synthesis,
        investigation_reasoning=investigation_reasoning,
        prior_evidence=prior_evidence,
        new_evidence=new_evidence,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Produce an updated insight integrating the investigation findings."},
    ]

    try:
        response = await asyncio.wait_for(
            llm.chat(messages, tools=None),
            timeout=_SYNTHESIS_TIMEOUT,
        )
        return response.content or "Investigation synthesis failed — no content returned."
    except Exception as exc:
        logger.error("Investigation synthesis failed: %s", exc, exc_info=True)
        return "Investigation synthesis could not be completed."


# ── Main Loop ─────────────────────────────────────────────────────────────


async def deep_think_loop(
    question: str,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str | None = None,
    history: list[dict] | None = None,
    ddl: str | None = None,
    documentation: str | None = None,
    stats_context: str | None = None,
    stats_groups: list[str] | None = None,
    clarification_enabled: bool = False,
    rag_retrieval: bool = True,
) -> AsyncGenerator[ChatChunk, None]:
    """Run the Deep Think 5W1H pipeline.

    Yields ChatChunk objects compatible with the existing SSE stream.
    """
    cid = conversation_id or ""

    effective_ddl = ddl or ""
    effective_docs = documentation or ""

    # ── Phase 1: Dimension Extraction ─────────────────────────────────
    yield ChatChunk(
        type="status",
        content="Analyzing question dimensions (WHO/WHAT/WHEN/WHERE/HOW)...",
        data={"agent": "deep_think", "phase": "dimension_extraction"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    dimensions = await _extract_dimensions(
        question=question,
        llm=llm,
        ddl=effective_ddl,
        documentation=effective_docs,
        history=history,
    )

    enrichment_plan: OrchestratorPlan | None = None
    if dimensions:
        enrichment_plan = _build_enrichment_plan(dimensions)
        why_intent = dimensions.get("why_intent", "")
        dims = dimensions.get("dimensions", {})
        uncovered = [k for k, v in dims.items() if v.get("status") == "uncovered"]

        yield ChatChunk(
            type="status",
            content=f"Dimensions mapped. Intent: {why_intent[:80]}. "
                    f"{'Uncovered: ' + ', '.join(uncovered) if uncovered else 'All dimensions covered.'}",
            data={
                "agent": "deep_think",
                "phase": "dimensions_complete",
                "dimensions": dims,
                "why_intent": why_intent,
                "enrichment_count": len(enrichment_plan.tasks) if enrichment_plan else 0,
            },
            conversation_id=cid,
            timestamp=time.time(),
        )
    else:
        logger.warning("Dimension extraction failed; proceeding with analyst only")
        yield ChatChunk(
            type="status",
            content="Dimension analysis unavailable, proceeding with direct analysis...",
            data={"agent": "deep_think", "phase": "dimensions_failed"},
            conversation_id=cid,
            timestamp=time.time(),
        )

    # ── Phase 2: Analyst (unchanged) ──────────────────────────────────
    collector = AnalystCollector()

    async for chunk in analyst_loop(
        question=question,
        llm=llm,
        db=db,
        rag=rag,
        config=config,
        conversation_id=conversation_id,
        history=history,
        ddl_override=ddl,
        documentation_override=documentation,
        stats_context=stats_context,
        stats_groups=stats_groups,
        clarification_enabled=clarification_enabled,
        rag_retrieval=rag_retrieval,
    ):
        yield chunk
        collector.process_chunk(chunk)

    # If analyst failed or no enrichment plan, stop here
    if collector.had_error or not collector.answer:
        logger.info("Deep think: analyst error=%s, answer_empty=%s — stopping",
                     collector.had_error, not collector.answer)
        return

    if not enrichment_plan or not enrichment_plan.tasks:
        logger.info("Deep think: no enrichment tasks planned — analyst answer stands")
        yield ChatChunk(
            type="status",
            content="Analysis complete",
            data={"agent": "deep_think", "phase": "done"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        return

    # ── Phase 3: Targeted Enrichment ──────────────────────────────────
    original = collector.to_original_result()

    yield ChatChunk(
        type="orchestrator_plan",
        data={
            "reasoning": enrichment_plan.reasoning,
            "tasks": [
                {
                    "id": t.id,
                    "agent": t.agent,
                    "task": t.task,
                    "depends_on": t.depends_on,
                    "category": t.category,
                }
                for t in enrichment_plan.tasks
            ],
        },
        content=f"Deep analysis: enriching {len(enrichment_plan.tasks)} dimension{'s' if len(enrichment_plan.tasks) != 1 else ''}",
        conversation_id=cid,
        timestamp=time.time(),
    )

    yield ChatChunk(
        type="status",
        content=f"Running {len(enrichment_plan.tasks)} enrichment task{'s' if len(enrichment_plan.tasks) != 1 else ''}...",
        data={"agent": "deep_think", "phase": "executing"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    pending_chunks, on_task_start, on_task_complete = build_dag_callbacks("deep_think", cid)

    async def run_task(task: SubTask, upstream: dict[str, SubTaskResult]) -> SubTaskResult:
        # Late import to avoid circular dependency
        from insightxpert.agents.orchestrator import _run_quant_analyst, _run_sql_analyst
        if task.agent == "quant_analyst":
            return await _run_quant_analyst(
                task=task,
                upstream=upstream,
                llm=llm,
                db=db,
                rag=rag,
                config=config,
                conversation_id=cid,
                ddl=effective_ddl,
                documentation=effective_docs,
            )
        return await _run_sql_analyst(
            task=task,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=cid,
            ddl_override=ddl,
            docs_override=documentation,
            stats_context=stats_context,
            stats_groups=stats_groups or [],
        )

    results = await execute_dag(
        plan=enrichment_plan,
        run_task=run_task,
        on_task_start=on_task_start,
        on_task_complete=on_task_complete,
    )

    # Yield collected status and trace chunks
    for chunk in pending_chunks:
        yield chunk
        await asyncio.sleep(0)

    # Enrichment trace chunks for citation system
    async for trace_chunk in yield_enrichment_traces(
        question=question,
        analyst_sql=collector.sql,
        analyst_answer=collector.answer,
        analyst_duration_ms=collector.duration_ms,
        plan=enrichment_plan,
        results=results,
        conversation_id=cid,
    ):
        yield trace_chunk

    # Check if any enrichment tasks succeeded
    successful = {tid: r for tid, r in results.items() if r.success}
    if not successful:
        logger.warning("All enrichment tasks failed; analyst answer stands")
        return

    # ── Phase 4: Deep Synthesis ───────────────────────────────────────
    yield ChatChunk(
        type="status",
        content="Synthesizing dimensional insight...",
        data={"agent": "deep_think", "phase": "synthesizing"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    synthesized = await _deep_synthesize(
        question=question,
        llm=llm,
        ddl=effective_ddl,
        documentation=effective_docs,
        original=original,
        plan=enrichment_plan,
        results=results,
        dimensions=dimensions or {},
    )

    # Evaluate if this synthesis qualifies as a genuine insight
    from insightxpert.agents.orchestrator_planner import evaluate_insight_quality

    categories = list({t.category for t in enrichment_plan.tasks if t.category})
    quality = await evaluate_insight_quality(
        question=question,
        synthesized_content=synthesized,
        categories=categories,
        enrichment_task_count=len(enrichment_plan.tasks),
        llm=llm,
    )

    yield ChatChunk(
        type="insight",
        content=synthesized,
        data={
            "agent": "deep_think",
            "save_as_insight": quality.is_insight,
            "insight_summary": quality.summary,
        },
        conversation_id=cid,
        timestamp=time.time(),
    )

    # ── Phase 5: Auto-execute investigation ──────────────────────────
    # In deep think mode, investigation runs automatically (no user click).
    try:
        from insightxpert.agents.orchestrator_planner import evaluate_for_investigation

        evidence_text = build_evidence_blocks(question, enrichment_plan, results, original)
        existing_ids = [t.id for t in enrichment_plan.tasks]
        investigation = await evaluate_for_investigation(
            question=question,
            analyst_sql=collector.sql,
            analyst_answer=collector.answer,
            enrichment_evidence=evidence_text,
            synthesized_insight=synthesized,
            existing_task_ids=existing_ids,
            llm=llm,
            ddl=effective_ddl,
            documentation=effective_docs,
        )

        if investigation and investigation.tasks:
            logger.info(
                "Deep think: auto-executing %d investigation tasks",
                len(investigation.tasks),
            )

            yield ChatChunk(
                type="orchestrator_plan",
                data={
                    "reasoning": investigation.reasoning,
                    "tasks": [
                        {
                            "id": t.id,
                            "agent": t.agent,
                            "task": t.task,
                            "depends_on": t.depends_on,
                            "category": t.category,
                        }
                        for t in investigation.tasks
                    ],
                },
                content=f"Investigating {len(investigation.tasks)} follow-up question{'s' if len(investigation.tasks) != 1 else ''}",
                conversation_id=cid,
                timestamp=time.time(),
            )

            yield ChatChunk(
                type="status",
                content=f"Running {len(investigation.tasks)} investigation quer{'ies' if len(investigation.tasks) != 1 else 'y'}...",
                data={"agent": "deep_think", "phase": "investigating"},
                conversation_id=cid,
                timestamp=time.time(),
            )

            # Execute investigation tasks
            inv_pending, inv_on_start, inv_on_complete = build_dag_callbacks("deep_think", cid)

            async def run_inv_task(task: SubTask, _upstream: dict[str, SubTaskResult]) -> SubTaskResult:
                from insightxpert.agents.orchestrator import _run_sql_analyst
                return await _run_sql_analyst(
                    task=task,
                    llm=llm,
                    db=db,
                    rag=rag,
                    config=config,
                    conversation_id=cid,
                    ddl_override=ddl,
                    docs_override=documentation,
                    stats_context=stats_context,
                    stats_groups=stats_groups or [],
                )

            inv_results = await execute_dag(
                plan=investigation,
                run_task=run_inv_task,
                on_task_start=inv_on_start,
                on_task_complete=inv_on_complete,
            )

            # Yield status chunks from investigation DAG
            for chunk in inv_pending:
                yield chunk
                await asyncio.sleep(0)

            # Yield enrichment traces for investigation sources
            # Source indices continue from enrichment: [1]=analyst, [2..N]=enrichment, [N+1..]=investigation
            source_offset = len(enrichment_plan.tasks) + 1  # +1 for original analyst
            for i, inv_task in enumerate(investigation.tasks, start=source_offset + 1):
                inv_result = inv_results.get(inv_task.id)
                if not inv_result or not inv_result.success:
                    continue
                category_label = CATEGORY_LABELS.get(
                    inv_task.category, inv_task.agent.replace("_", " ").title(),
                )
                yield ChatChunk(
                    type="enrichment_trace",
                    data={
                        "source_index": i,
                        "category": category_label,
                        "question": inv_task.task,
                        "rationale": investigation.reasoning,
                        "final_sql": inv_result.sql,
                        "final_answer": inv_result.answer,
                        "success": True,
                        "duration_ms": inv_result.duration_ms,
                        "steps": inv_result.trace_steps or [],
                    },
                    conversation_id=cid,
                    timestamp=time.time(),
                )
                await asyncio.sleep(0)

            # Re-synthesize if any investigation tasks succeeded
            inv_successful = {tid: r for tid, r in inv_results.items() if r.success}
            if inv_successful:
                yield ChatChunk(
                    type="status",
                    content="Integrating investigation findings...",
                    data={"agent": "deep_think", "phase": "re_synthesizing"},
                    conversation_id=cid,
                    timestamp=time.time(),
                )

                new_evidence = build_evidence_blocks(question, investigation, inv_results)

                re_synthesized = await _investigation_synthesize(
                    question=question,
                    llm=llm,
                    ddl=effective_ddl,
                    documentation=effective_docs,
                    prior_synthesis=synthesized,
                    investigation_reasoning=investigation.reasoning,
                    prior_evidence=evidence_text,
                    new_evidence=new_evidence,
                )

                yield ChatChunk(
                    type="insight",
                    content=re_synthesized,
                    data={
                        "agent": "deep_think",
                        "investigation": True,
                        "save_as_insight": quality.is_insight,
                        "insight_summary": quality.summary,
                    },
                    conversation_id=cid,
                    timestamp=time.time(),
                )
            else:
                logger.warning("All investigation tasks failed; prior synthesis stands")
    except Exception as exc:
        logger.warning("Investigation auto-execution failed, prior synthesis stands: %s", exc)
