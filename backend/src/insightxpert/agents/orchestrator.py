"""Orchestrator agent -- analyst-first agentic pipeline.

Implements the top-level question-answering flow with two modes:

**basic mode:** Runs analyst_loop only — direct SQL generation and answer.

**agentic mode:** Analyst runs first (user sees results immediately), then an
evaluator decides if enrichment is needed.  If yes, additional targeted tasks
run via DAG, and a synthesizer combines everything into a cited insight.

Legacy modes (auto, statistician, advanced, analyst) are mapped accordingly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
    SubTask,
    SubTaskResult,
    execute_dag,
)
from insightxpert.agents.orchestrator_planner import (
    evaluate_for_enrichment,
    evaluate_insight_quality,
)
from insightxpert.agents.quant_analyst import quant_analyst_loop
from insightxpert.agents.response_generator import generate_response
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
    agent_mode: str = "agentic",
    dataset_service=None,
    skip_clarification: bool = False,
    stats_context_injection: bool = False,
    clarification_enabled: bool = False,
    rag_retrieval: bool = True,
    investigation_tasks: list[dict] | None = None,
    prior_evidence: str | None = None,
    investigation_reasoning: str | None = None,
) -> AsyncGenerator[ChatChunk, None]:
    """Run the orchestrator pipeline.

    agent_mode:
        "basic"    -- analyst only (no orchestration)
        "agentic"  -- analyst-first with conditional enrichment
        Other      -- mapped to "agentic" for backward compatibility
    """
    # Backward compat: map legacy modes
    if agent_mode == "analyst":
        agent_mode = "basic"
    elif agent_mode not in ("basic", "agentic", "deep"):
        logger.info("Mapping legacy agent_mode=%r to 'agentic'", agent_mode)
        agent_mode = "agentic"

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

    effective_ddl = ddl_override or DDL
    effective_docs = docs_override or DOCUMENTATION

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

    cid = conversation_id or ""

    # --- Investigation follow-up early return ---
    if investigation_tasks:
        async for chunk in _run_investigation_followup(
            question=question,
            investigation_tasks=investigation_tasks,
            prior_evidence=prior_evidence or "",
            investigation_reasoning=investigation_reasoning or "",
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=cid,
            ddl=effective_ddl,
            documentation=effective_docs,
            ddl_override=ddl_override,
            docs_override=docs_override,
            stats_context=stats_context,
            stats_groups=stats_groups,
        ):
            yield chunk
        return

    if agent_mode == "basic":
        # --- Basic mode: analyst only (no orchestration) ---
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
            rag_retrieval=rag_retrieval,
        ):
            yield chunk
        return

    if agent_mode == "deep":
        # --- Deep Think mode: 5W1H dimensional analysis ---
        from insightxpert.agents.deep_think import deep_think_loop

        async for chunk in deep_think_loop(
            question=question,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=conversation_id,
            history=history,
            ddl=effective_ddl,
            documentation=effective_docs,
            stats_context=stats_context,
            stats_groups=stats_groups,
            clarification_enabled=effective_clarification,
            rag_retrieval=rag_retrieval,
            investigation_tasks=investigation_tasks,
            prior_evidence=prior_evidence,
            investigation_reasoning=investigation_reasoning,
        ):
            yield chunk
        return

    # --- Agentic mode: analyst-first with conditional enrichment ---

    # ── Phase 1: Run analyst with the original question ──────────────
    # User sees results immediately (sql, table, chart, answer).
    collector = AnalystCollector()

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
        rag_retrieval=rag_retrieval,
    ):
        yield chunk
        collector.process_chunk(chunk)

    # If analyst failed or returned a clarification, stop here
    if collector.had_error or not collector.answer:
        logger.info("Skipping enrichment: error=%s, answer_empty=%s", collector.had_error, not collector.answer)
        return

    # ── Phase 2: Evaluate whether enrichment is needed ───────────────
    logger.info("Phase 2: evaluating enrichment (analyst_sql=%s, rows=%d, answer_len=%d)",
                bool(collector.sql), len(collector.rows), len(collector.answer))
    yield ChatChunk(
        type="status",
        content="Evaluating if deeper analysis is needed...",
        data={"agent": "orchestrator", "phase": "evaluating"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    # RAG retrieval for evaluator context (skipped when rag_retrieval=False)
    rag_context: list[dict] = []
    if rag_retrieval:
        try:
            similar = rag.search_qa(question, n=3)
            rag_context = [
                {"question": doc.get("question", ""), "sql": doc.get("sql", "")}
                for doc in similar
                if doc.get("distance", 999) <= 1.0
            ]
        except Exception as e:
            logger.debug("RAG retrieval for evaluator failed: %s", e)

    enrichment_plan = await evaluate_for_enrichment(
        question=question,
        analyst_sql=collector.sql,
        analyst_rows=collector.rows,
        analyst_answer=collector.answer,
        llm=llm,
        ddl=effective_ddl,
        documentation=effective_docs,
        history=history,
        rag_context=rag_context,
        max_tasks=config.max_orchestrator_tasks,
    )

    if enrichment_plan is None:
        # Analyst answer is sufficient — no enrichment needed
        logger.info("Enrichment not needed; analyst answer stands")
        yield ChatChunk(
            type="status",
            content="Analysis complete",
            data={"agent": "orchestrator", "phase": "done"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        return

    # ── Phase 3: Execute additional enrichment tasks via DAG ─────────
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
        content=f"Enriching with {len(enrichment_plan.tasks)} additional task{'s' if len(enrichment_plan.tasks) != 1 else ''}",
        conversation_id=cid,
        timestamp=time.time(),
    )

    yield ChatChunk(
        type="status",
        content=f"Running {len(enrichment_plan.tasks)} enrichment task{'s' if len(enrichment_plan.tasks) != 1 else ''}...",
        data={"agent": "orchestrator", "phase": "executing"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    pending_chunks, on_task_start, on_task_complete = build_dag_callbacks("orchestrator", cid)

    async def run_task(task: SubTask, upstream: dict[str, SubTaskResult]) -> SubTaskResult:
        if task.agent == "sql_analyst":
            return await _run_sql_analyst(
                task=task,
                llm=llm,
                db=db,
                rag=rag,
                config=config,
                conversation_id=cid,
                ddl_override=ddl_override,
                docs_override=docs_override,
                stats_context=stats_context,
                stats_groups=stats_groups,
            )
        elif task.agent == "quant_analyst":
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
        else:
            return SubTaskResult(
                success=False,
                error=f"Unknown agent type: {task.agent}",
            )

    results = await execute_dag(
        plan=enrichment_plan,
        run_task=run_task,
        on_task_start=on_task_start,
        on_task_complete=on_task_complete,
    )

    # Yield all collected status and trace chunks
    for chunk in pending_chunks:
        yield chunk
        await asyncio.sleep(0)

    # ── Phase 5: Enrichment trace chunks for citation system ─────────
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

    # ── Phase 4: Synthesize original + additional into cited insight ──
    yield ChatChunk(
        type="status",
        content="Synthesizing final response...",
        data={"agent": "orchestrator", "phase": "synthesizing"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    synthesized = await generate_response(
        question=question,
        plan=enrichment_plan,
        results=results,
        llm=llm,
        ddl=effective_ddl,
        documentation=effective_docs,
        original_analyst=original,
    )

    # Evaluate if this synthesis qualifies as a genuine insight
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
            "agent": "orchestrator",
            "save_as_insight": quality.is_insight,
            "insight_summary": quality.summary,
        },
        conversation_id=cid,
        timestamp=time.time(),
    )

    # Investigation is a deep think feature only — agentic mode stops here.


async def _run_sql_analyst(
    task: SubTask,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str,
    ddl_override: str | None,
    docs_override: str | None,
    stats_context: str | None,
    stats_groups: list[str],
) -> SubTaskResult:
    """Run analyst_loop for a sub-task and collect results."""
    collected_sql = ""
    collected_rows: list[dict] = []
    collected_answer = ""
    trace_steps: list[dict] = []
    t0 = time.time()

    try:
        async for chunk in analyst_loop(
            question=task.task,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=conversation_id,
            history=None,
            ddl_override=ddl_override,
            documentation_override=docs_override,
            stats_context=stats_context,
            stats_groups=stats_groups,
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
                if tool_name == "run_sql" and chunk.data.get("result"):
                    try:
                        parsed = json.loads(chunk.data["result"])
                        rows = parsed.get("rows", [])
                        if rows:
                            collected_rows = rows
                            # Store structured result for trace display
                            display_data = {
                                "columns": parsed.get("columns", list(rows[0].keys()) if rows else []),
                                "rows": rows[:50],
                                "row_count": len(rows),
                            }
                            step["result_data"] = json.dumps(display_data)
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

        return SubTaskResult(
            sql=collected_sql,
            rows=collected_rows,
            answer=collected_answer,
            success=bool(collected_answer),
            trace_steps=trace_steps,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        logger.warning("SQL analyst task %s failed: %s", task.id, exc)
        return SubTaskResult(
            success=False,
            error=str(exc),
            trace_steps=trace_steps,
            duration_ms=duration_ms,
        )


async def _run_quant_analyst(
    task: SubTask,
    upstream: dict[str, SubTaskResult],
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str,
    ddl: str,
    documentation: str,
) -> SubTaskResult:
    """Run quant_analyst_loop for a sub-task and collect results."""
    collected_answer = ""
    trace_steps: list[dict] = []
    t0 = time.time()

    try:
        async for chunk in quant_analyst_loop(
            task=task.task,
            upstream_results=upstream,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=conversation_id,
            ddl=ddl,
            documentation=documentation,
        ):
            step: dict = {
                "type": chunk.type,
                "timestamp": chunk.timestamp or time.time(),
            }

            if chunk.type == "tool_call":
                step["tool_name"] = chunk.tool_name or ""
                step["tool_args"] = chunk.args or {}
            elif chunk.type == "tool_result" and chunk.data:
                step["tool_name"] = chunk.data.get("tool", "")
                result_str = str(chunk.data.get("result", ""))
                step["result_preview"] = result_str[:500]
                # Store structured result for trace display
                if chunk.data.get("result"):
                    try:
                        parsed_r = json.loads(str(chunk.data["result"]))
                        r = parsed_r.get("rows", [])
                        if r:
                            step["result_data"] = json.dumps({
                                "columns": parsed_r.get("columns", list(r[0].keys()) if r else []),
                                "rows": r[:50],
                                "row_count": len(r),
                            })
                    except (json.JSONDecodeError, AttributeError, TypeError):
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

        return SubTaskResult(
            answer=collected_answer,
            success=bool(collected_answer),
            trace_steps=trace_steps,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        logger.warning("Quant analyst task %s failed: %s", task.id, exc)
        return SubTaskResult(
            success=False,
            error=str(exc),
            trace_steps=trace_steps,
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# Investigation follow-up (stateless re-entry)
# ---------------------------------------------------------------------------


async def _run_investigation_followup(
    question: str,
    investigation_tasks: list[dict],
    prior_evidence: str,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str,
    ddl: str,
    documentation: str,
    ddl_override: str | None = None,
    docs_override: str | None = None,
    stats_context: str | None = None,
    stats_groups: list[str] | None = None,
    investigation_reasoning: str = "",
) -> AsyncGenerator[ChatChunk, None]:
    """Execute investigation follow-up tasks and re-synthesize with combined evidence.

    This is the stateless re-entry path when the user clicks "Investigate".
    The frontend sends the follow-up tasks + prior_evidence from the suggestion chunk.
    """
    cid = conversation_id

    # Parse investigation tasks into SubTask objects
    tasks: list[SubTask] = []
    for item in investigation_tasks:
        task_id = str(item.get("id", "")).upper()
        task_desc = str(item.get("task", ""))
        category = str(item.get("category", "")).lower()
        if not task_id or not task_desc:
            continue
        tasks.append(SubTask(
            id=task_id,
            agent="sql_analyst",
            task=task_desc,
            depends_on=[],
            category=category,
        ))

    if not tasks:
        yield ChatChunk(
            type="status",
            content="No valid investigation tasks found",
            data={"agent": "orchestrator", "phase": "investigation_failed"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        return

    plan = OrchestratorPlan(
        reasoning=investigation_reasoning or "Follow-up investigation to fill analytical gaps",
        tasks=tasks,
    )

    yield ChatChunk(
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
        content=f"Investigating {len(plan.tasks)} follow-up question{'s' if len(plan.tasks) != 1 else ''}",
        conversation_id=cid,
        timestamp=time.time(),
    )

    yield ChatChunk(
        type="status",
        content=f"Running {len(plan.tasks)} investigation task{'s' if len(plan.tasks) != 1 else ''}...",
        data={"agent": "orchestrator", "phase": "investigating"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    pending_chunks, on_task_start, on_task_complete = build_dag_callbacks("orchestrator", cid)

    async def run_task(task: SubTask, _upstream: dict[str, SubTaskResult]) -> SubTaskResult:
        return await _run_sql_analyst(
            task=task,
            llm=llm,
            db=db,
            rag=rag,
            config=config,
            conversation_id=cid,
            ddl_override=ddl_override,
            docs_override=docs_override,
            stats_context=stats_context,
            stats_groups=stats_groups or [],
        )

    results = await execute_dag(
        plan=plan,
        run_task=run_task,
        on_task_start=on_task_start,
        on_task_complete=on_task_complete,
    )

    # Yield collected status and trace chunks
    for chunk in pending_chunks:
        yield chunk
        await asyncio.sleep(0)

    # Enrichment traces for follow-up tasks (source indices continue from prior)
    # Count existing sources from prior_evidence
    source_matches = re.findall(r"### Source \[(\d+)\]", prior_evidence)
    source_offset = max((int(m) for m in source_matches), default=0) if source_matches else 0

    for i, task in enumerate(plan.tasks, start=source_offset + 1):
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
                "rationale": "Follow-up investigation",
                "final_sql": result.sql,
                "final_answer": result.answer,
                "success": True,
                "duration_ms": result.duration_ms,
                "steps": result.trace_steps or [],
            },
            conversation_id=cid,
            timestamp=time.time(),
        )
        await asyncio.sleep(0)

    # Check if any investigation tasks succeeded
    successful = {tid: r for tid, r in results.items() if r.success}
    if not successful:
        logger.warning("All investigation tasks failed")
        yield ChatChunk(
            type="status",
            content="Investigation did not produce results",
            data={"agent": "orchestrator", "phase": "investigation_failed"},
            conversation_id=cid,
            timestamp=time.time(),
        )
        return

    # Build new evidence from follow-up results
    new_evidence = build_evidence_blocks(question, plan, results)

    yield ChatChunk(
        type="status",
        content="Integrating investigation findings...",
        data={"agent": "orchestrator", "phase": "re_synthesizing"},
        conversation_id=cid,
        timestamp=time.time(),
    )

    # Re-synthesize using the investigation-focused template.
    # This template separates prior vs new evidence and focuses on what changed.
    from insightxpert.prompts import render as render_prompt
    from insightxpert.agents.response_generator import _fallback_answer

    # Extract investigation reasoning from the plan
    inv_reasoning = plan.reasoning or "Follow-up investigation to fill analytical gaps"

    system_prompt = render_prompt(
        "investigation_synthesizer.j2",
        ddl=ddl,
        documentation=documentation,
        question=question,
        prior_synthesis="",  # not available in user-initiated flow
        investigation_reasoning=inv_reasoning,
        prior_evidence=prior_evidence or "(no prior evidence)",
        new_evidence=new_evidence,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Produce an updated insight integrating the investigation findings."},
    ]

    try:
        response = await llm.chat(messages, tools=None)
        re_synthesized = response.content or _fallback_answer(plan, results)
    except Exception as exc:
        logger.error("Investigation re-synthesis failed: %s", exc, exc_info=True)
        re_synthesized = _fallback_answer(plan, results)

    # Evaluate if this investigation result qualifies as an insight
    inv_categories = list({t.category for t in plan.tasks if t.category})
    inv_quality = await evaluate_insight_quality(
        question=question,
        synthesized_content=re_synthesized,
        categories=inv_categories,
        enrichment_task_count=len(plan.tasks),
        llm=llm,
    )

    yield ChatChunk(
        type="insight",
        content=re_synthesized,
        data={
            "agent": "orchestrator",
            "investigation": True,
            "save_as_insight": inv_quality.is_insight,
            "insight_summary": inv_quality.summary,
        },
        conversation_id=cid,
        timestamp=time.time(),
    )
