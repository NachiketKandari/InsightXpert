"""Tests for _validate_plan demotion and dependency logic."""

import pytest

from insightxpert.agents.orchestrator_planner import _validate_plan


def _plan(tasks: list[dict], reasoning: str = "") -> dict:
    return {"reasoning": reasoning, "tasks": tasks}


class TestQuantAnalystDemotion:
    """quant_analyst with no dependencies must be demoted to sql_analyst."""

    def test_quant_no_deps_demoted(self):
        parsed = _plan([
            {"id": "B", "agent": "quant_analyst", "task": "run chi-squared", "depends_on": []},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        assert plan.tasks[0].agent == "sql_analyst"

    def test_quant_with_valid_dep_kept(self):
        parsed = _plan([
            {"id": "B", "agent": "sql_analyst", "task": "fetch data"},
            {"id": "C", "agent": "quant_analyst", "task": "run chi-squared", "depends_on": ["B"]},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        task_c = next(t for t in plan.tasks if t.id == "C")
        assert task_c.agent == "quant_analyst"
        assert task_c.depends_on == ["B"]

    def test_quant_with_dangling_dep_demoted(self):
        """If quant_analyst depends on a task ID that doesn't exist, the dep
        is pruned and the task is demoted."""
        parsed = _plan([
            {"id": "B", "agent": "quant_analyst", "task": "run stats", "depends_on": ["Z"]},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        assert plan.tasks[0].agent == "sql_analyst"
        assert plan.tasks[0].depends_on == []

    def test_sql_analyst_no_deps_unchanged(self):
        parsed = _plan([
            {"id": "B", "agent": "sql_analyst", "task": "fetch data", "depends_on": []},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        assert plan.tasks[0].agent == "sql_analyst"

    def test_multiple_quants_mixed(self):
        """Only orphaned quant_analysts are demoted; ones with deps survive."""
        parsed = _plan([
            {"id": "B", "agent": "sql_analyst", "task": "fetch data"},
            {"id": "C", "agent": "quant_analyst", "task": "orphan stats", "depends_on": []},
            {"id": "D", "agent": "quant_analyst", "task": "valid stats", "depends_on": ["B"]},
        ])
        plan = _validate_plan(parsed, max_tasks=5)
        task_c = next(t for t in plan.tasks if t.id == "C")
        task_d = next(t for t in plan.tasks if t.id == "D")
        assert task_c.agent == "sql_analyst"
        assert task_d.agent == "quant_analyst"


class TestDependencyPruning:
    """References to non-existent task IDs are removed."""

    def test_prunes_nonexistent_deps(self):
        parsed = _plan([
            {"id": "B", "agent": "sql_analyst", "task": "query", "depends_on": ["X", "Y"]},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        assert plan.tasks[0].depends_on == []

    def test_keeps_valid_deps(self):
        parsed = _plan([
            {"id": "B", "agent": "sql_analyst", "task": "first query"},
            {"id": "C", "agent": "sql_analyst", "task": "second", "depends_on": ["B"]},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        task_c = next(t for t in plan.tasks if t.id == "C")
        assert task_c.depends_on == ["B"]


class TestCycleDetection:
    def test_circular_deps_cleared(self):
        parsed = _plan([
            {"id": "B", "agent": "sql_analyst", "task": "q1", "depends_on": ["C"]},
            {"id": "C", "agent": "sql_analyst", "task": "q2", "depends_on": ["B"]},
        ])
        plan = _validate_plan(parsed, max_tasks=4)
        for t in plan.tasks:
            assert t.depends_on == []
