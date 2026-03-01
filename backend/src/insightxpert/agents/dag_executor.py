"""DAG-based task execution engine for the multi-agent orchestrator.

Decomposes analytical questions into a directed acyclic graph of sub-tasks
and executes them with maximum parallelism while respecting dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger("insightxpert.dag_executor")


@dataclass
class OriginalAnalystResult:
    """Captures the Phase 1 analyst output for use in enrichment evaluation and synthesis."""

    sql: str = ""
    rows: list[dict] = field(default_factory=list)
    answer: str = ""
    duration_ms: int = 0


@dataclass
class SubTaskResult:
    """Result produced by a single sub-task execution."""

    sql: str | None = None
    rows: list[dict] = field(default_factory=list)
    answer: str = ""
    success: bool = False
    error: str | None = None
    trace_steps: list[dict] | None = None
    duration_ms: int | None = None


@dataclass
class SubTask:
    """A single node in the orchestrator's execution DAG."""

    id: str                               # "A", "B", "C", ...
    agent: str                            # "sql_analyst" | "quant_analyst"
    task: str                             # Natural-language task description
    depends_on: list[str] = field(default_factory=list)
    category: str = ""                    # comparative_context | temporal_trend | root_cause | segmentation
    status: str = "pending"               # pending | running | done | error | skipped
    result: SubTaskResult | None = None


@dataclass
class OrchestratorPlan:
    """The orchestrator's decomposition of a user question into sub-tasks."""

    reasoning: str
    tasks: list[SubTask] = field(default_factory=list)


async def execute_dag(
    plan: OrchestratorPlan,
    run_task: Callable[[SubTask, dict[str, SubTaskResult]], Awaitable[SubTaskResult]],
    on_task_start: Callable[[SubTask], Awaitable[None]] | None = None,
    on_task_complete: Callable[[SubTask], Awaitable[None]] | None = None,
) -> dict[str, SubTaskResult]:
    """Execute a DAG of sub-tasks with maximum parallelism.

    Args:
        plan: The orchestrator plan containing sub-tasks with dependencies.
        run_task: Async callable that executes a single sub-task. Receives the
            task and a dict of upstream results (keyed by task ID).
        on_task_start: Optional callback fired when a task begins execution.
        on_task_complete: Optional callback fired when a task finishes.

    Returns:
        Dict mapping task ID to its SubTaskResult.
    """
    results: dict[str, SubTaskResult] = {}
    completed: set[str] = set()
    task_map = {t.id: t for t in plan.tasks}

    # Validate: all depends_on IDs must exist in the plan
    all_ids = set(task_map.keys())
    for t in plan.tasks:
        unknown = set(t.depends_on) - all_ids
        if unknown:
            logger.warning("Task %s depends on unknown IDs: %s", t.id, unknown)
            t.depends_on = [d for d in t.depends_on if d in all_ids]

    while len(completed) < len(plan.tasks):
        # Find runnable tasks: pending with all deps satisfied
        runnable = [
            t for t in plan.tasks
            if t.status == "pending" and all(d in completed for d in t.depends_on)
        ]

        if not runnable:
            # Check for deadlock: remaining tasks exist but none are runnable
            remaining = [t for t in plan.tasks if t.status not in ("done", "error", "skipped")]
            if remaining:
                logger.error(
                    "DAG deadlock: %d tasks remain but none are runnable: %s",
                    len(remaining),
                    [t.id for t in remaining],
                )
                for t in remaining:
                    t.status = "error"
                    t.result = SubTaskResult(
                        success=False,
                        error="Deadlock: dependencies could not be resolved",
                    )
                    results[t.id] = t.result
                    completed.add(t.id)
            break

        # Launch all runnable tasks in parallel
        async def _run_one(task: SubTask) -> None:
            task.status = "running"
            if on_task_start:
                await on_task_start(task)

            upstream = {dep_id: results[dep_id] for dep_id in task.depends_on if dep_id in results}

            try:
                result = await run_task(task, upstream)
                task.result = result
                task.status = "done" if result.success else "error"
                results[task.id] = result
            except Exception as exc:
                logger.error("Task %s failed with exception: %s", task.id, exc, exc_info=True)
                task.status = "error"
                task.result = SubTaskResult(success=False, error=str(exc))
                results[task.id] = task.result

            completed.add(task.id)

            if on_task_complete:
                await on_task_complete(task)

            # On failure, skip dependent tasks
            if task.status == "error":
                _skip_dependents(task.id, plan.tasks, results, completed)

        await asyncio.gather(*[_run_one(t) for t in runnable])

    return results


def _skip_dependents(
    failed_id: str,
    all_tasks: list[SubTask],
    results: dict[str, SubTaskResult],
    completed: set[str],
) -> None:
    """Recursively mark tasks that depend on a failed task as skipped."""
    for t in all_tasks:
        if t.status == "pending" and failed_id in t.depends_on:
            t.status = "skipped"
            t.result = SubTaskResult(
                success=False,
                error=f"Skipped: upstream task {failed_id} failed",
            )
            results[t.id] = t.result
            completed.add(t.id)
            logger.info("Task %s skipped due to failed dependency %s", t.id, failed_id)
            # Recursively skip further dependents
            _skip_dependents(t.id, all_tasks, results, completed)
