"""Orchestrator planner — question decomposition and enrichment evaluation.

Provides two functions:

1. ``plan_tasks()`` — Decomposes a user question into a DAG of sub-tasks
   (used for backward compatibility / direct planning).

2. ``evaluate_for_enrichment()`` — Given the analyst's actual results, decides
   whether additional analysis tasks would meaningfully improve the answer.
   Returns ``None`` if sufficient, or an ``OrchestratorPlan`` of additional tasks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from insightxpert.agents.dag_executor import OrchestratorPlan, SubTask
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt

logger = logging.getLogger("insightxpert.orchestrator_planner")

_VALID_AGENTS = {"sql_analyst", "quant_analyst"}
_MAX_TASKS = 5


async def plan_tasks(
    question: str,
    llm: LLMProvider,
    *,
    ddl: str,
    documentation: str,
    history: list[dict] | None = None,
    rag_context: list[dict] | None = None,
    max_tasks: int = _MAX_TASKS,
) -> OrchestratorPlan:
    """Decompose a user question into an OrchestratorPlan via a single LLM call.

    On any parse or validation failure, falls back to a single sql_analyst task.
    """
    system_prompt = render_prompt(
        "orchestrator_planner.j2",
        ddl=ddl,
        documentation=documentation,
        rag_context=rag_context or [],
        max_tasks=max_tasks,
    )

    history_block = ""
    if history:
        recent = history[-6:]  # last 3 turns (user+assistant pairs)
        lines = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")[:300]
            lines.append(f"**{role}:** {content}")
        history_block = "\n".join(lines)

    user_message = f"Question: {question}"
    if history_block:
        user_message = f"Recent conversation:\n{history_block}\n\n{user_message}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    t0 = time.time()
    try:
        response = await llm.chat(messages, tools=None)
        raw = (response.content or "").strip()
        planning_ms = int((time.time() - t0) * 1000)

        # Strip markdown fencing if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)
        plan = _validate_plan(parsed, max_tasks)

        logger.info(
            "Orchestrator planner produced %d tasks in %dms: %s",
            len(plan.tasks),
            planning_ms,
            [(t.id, t.agent) for t in plan.tasks],
        )
        return plan

    except Exception as exc:
        planning_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "Orchestrator planner failed (%dms), falling back to single task: %s",
            planning_ms,
            exc,
            exc_info=True,
        )
        return _fallback_plan(question)


def _validate_plan(parsed: dict, max_tasks: int) -> OrchestratorPlan:
    """Validate and normalize a parsed JSON plan from the LLM."""
    reasoning = parsed.get("reasoning", "")
    tasks_raw = parsed.get("tasks", [])

    if not tasks_raw or not isinstance(tasks_raw, list):
        raise ValueError("Plan has no tasks array")

    tasks_raw = tasks_raw[:max_tasks]

    tasks: list[SubTask] = []
    seen_ids: set[str] = set()

    for item in tasks_raw:
        task_id = str(item.get("id", "")).upper()
        agent = str(item.get("agent", "sql_analyst"))
        task_desc = str(item.get("task", ""))
        depends_on = item.get("depends_on", [])

        if not task_id or not task_desc:
            continue

        if agent not in _VALID_AGENTS:
            agent = "sql_analyst"

        if isinstance(depends_on, str):
            depends_on = [depends_on]
        depends_on = [str(d).upper() for d in depends_on if d]

        seen_ids.add(task_id)
        tasks.append(SubTask(
            id=task_id,
            agent=agent,
            task=task_desc,
            depends_on=depends_on,
        ))

    if not tasks:
        raise ValueError("No valid tasks after validation")

    # Remove references to non-existent task IDs
    for t in tasks:
        t.depends_on = [d for d in t.depends_on if d in seen_ids]

    # Check for circular dependencies
    if _has_cycle(tasks):
        logger.warning("Circular dependency detected, removing all dependencies")
        for t in tasks:
            t.depends_on = []

    return OrchestratorPlan(reasoning=reasoning, tasks=tasks)


def _has_cycle(tasks: list[SubTask]) -> bool:
    """Detect circular dependencies via topological sort (Kahn's algorithm)."""
    in_degree: dict[str, int] = {t.id: 0 for t in tasks}
    adjacency: dict[str, list[str]] = {t.id: [] for t in tasks}

    for t in tasks:
        for dep in t.depends_on:
            if dep in adjacency:
                adjacency[dep].append(t.id)
                in_degree[t.id] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    visited = 0

    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adjacency.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return visited < len(tasks)


def _fallback_plan(question: str) -> OrchestratorPlan:
    """Create a single sql_analyst task as fallback."""
    return OrchestratorPlan(
        reasoning="Falling back to single SQL analyst task.",
        tasks=[SubTask(id="A", agent="sql_analyst", task=question)],
    )


# ---------------------------------------------------------------------------
# Enrichment evaluator (analyst-first flow)
# ---------------------------------------------------------------------------

_MAX_ENRICHMENT_TASKS = 4
_EVALUATOR_TIMEOUT_SECONDS = 60


async def evaluate_for_enrichment(
    question: str,
    analyst_sql: str,
    analyst_rows: list[dict],
    analyst_answer: str,
    llm: LLMProvider,
    *,
    ddl: str,
    documentation: str,
    history: list[dict] | None = None,
    rag_context: list[dict] | None = None,
    max_tasks: int = _MAX_ENRICHMENT_TASKS,
) -> OrchestratorPlan | None:
    """Evaluate whether the analyst's answer needs enrichment.

    Returns ``None`` if the answer is sufficient, or an ``OrchestratorPlan``
    with additional tasks (IDs starting at "B") if enrichment is warranted.

    On any failure, returns ``None`` — the analyst answer stands as-is.
    """
    from insightxpert.agents.common import summarize_results

    rows_summary = summarize_results(analyst_rows, max_rows=10)

    system_prompt = render_prompt(
        "enrichment_evaluator.j2",
        ddl=ddl,
        documentation=documentation,
        question=question,
        analyst_sql=analyst_sql,
        analyst_rows=analyst_rows,
        analyst_rows_summary=rows_summary,
        analyst_answer=analyst_answer,
        rag_context=rag_context or [],
        history=history[-6:] if history else [],
        max_tasks=max_tasks,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Should this answer be enriched with additional analysis?"},
    ]

    t0 = time.time()
    try:
        logger.info("Enrichment evaluator starting (rows=%d, answer_len=%d)", len(analyst_rows), len(analyst_answer))
        response = await asyncio.wait_for(
            llm.chat(messages, tools=None),
            timeout=_EVALUATOR_TIMEOUT_SECONDS,
        )
        raw = (response.content or "").strip()
        eval_ms = int((time.time() - t0) * 1000)

        # Strip markdown fencing
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)

        if not parsed.get("enrich", False):
            logger.info("Enrichment evaluator says NO enrichment needed (%dms)", eval_ms)
            return None

        # Parse enrichment plan
        plan = _validate_plan(parsed, max_tasks)
        logger.info(
            "Enrichment evaluator produced %d additional tasks in %dms: %s",
            len(plan.tasks),
            eval_ms,
            [(t.id, t.agent) for t in plan.tasks],
        )
        return plan

    except asyncio.TimeoutError:
        eval_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "Enrichment evaluator timed out after %dms (limit=%ds), no enrichment",
            eval_ms, _EVALUATOR_TIMEOUT_SECONDS,
        )
        return None
    except Exception as exc:
        eval_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "Enrichment evaluator failed (%dms), no enrichment: %s",
            eval_ms,
            exc,
        )
        return None
