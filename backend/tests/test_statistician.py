"""Tests for the statistician agent and statistical tools."""

from __future__ import annotations

import json

import pytest

from .conftest import MockLLM
from insightxpert.agents.stat_tools import (
    ComputeCorrelationTool,
    ComputeDescriptiveStatsTool,
    FitDistributionTool,
    RunPythonTool,
    TestHypothesisTool,
    statistician_registry,
)
from insightxpert.agents.statistician import statistician_loop
from insightxpert.agents.tool_base import ToolContext
from insightxpert.llm.base import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RESULTS = [
    {"city": "Mumbai", "amount": 1500.0, "txn_type": "UPI", "status": "SUCCESS"},
    {"city": "Mumbai", "amount": 2500.0, "txn_type": "UPI", "status": "FAILED"},
    {"city": "Delhi", "amount": 800.0, "txn_type": "NEFT", "status": "SUCCESS"},
    {"city": "Delhi", "amount": 1200.0, "txn_type": "NEFT", "status": "SUCCESS"},
    {"city": "Mumbai", "amount": 3000.0, "txn_type": "UPI", "status": "SUCCESS"},
    {"city": "Delhi", "amount": 500.0, "txn_type": "NEFT", "status": "FAILED"},
    {"city": "Bangalore", "amount": 4500.0, "txn_type": "IMPS", "status": "SUCCESS"},
    {"city": "Bangalore", "amount": 2000.0, "txn_type": "IMPS", "status": "SUCCESS"},
    {"city": "Mumbai", "amount": 1800.0, "txn_type": "UPI", "status": "SUCCESS"},
    {"city": "Delhi", "amount": 900.0, "txn_type": "NEFT", "status": "SUCCESS"},
]

SAMPLE_SQL = "SELECT city, amount, txn_type, status FROM transactions LIMIT 10"


def _make_context(db, rag, results=None, sql=None) -> ToolContext:
    return ToolContext(
        db=db,
        rag=rag,
        analyst_results=results or SAMPLE_RESULTS,
        analyst_sql=sql or SAMPLE_SQL,
    )


# ---------------------------------------------------------------------------
# Tool Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_descriptive_stats(db_connector, rag_store):
    tool = ComputeDescriptiveStatsTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {"column": "amount"}))

    assert result["count"] == 10
    assert result["min"] == 500.0
    assert result["max"] == 4500.0
    assert "mean" in result
    assert "std" in result
    assert "skewness" in result
    assert "kurtosis" in result
    assert "median" in result
    assert "q1" in result
    assert "q3" in result


@pytest.mark.asyncio
async def test_descriptive_stats_missing_column(db_connector, rag_store):
    tool = ComputeDescriptiveStatsTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {"column": "nonexistent"}))
    assert "error" in result


@pytest.mark.asyncio
async def test_hypothesis_chi_squared(db_connector, rag_store):
    tool = TestHypothesisTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "test": "chi_squared",
        "category_col_1": "city",
        "category_col_2": "txn_type",
    }))
    assert result["test"] == "chi_squared"
    assert "statistic" in result
    assert "p_value" in result
    assert "effect_size_cramers_v" in result


@pytest.mark.asyncio
async def test_hypothesis_t_test(db_connector, rag_store):
    tool = TestHypothesisTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "test": "t_test",
        "column": "amount",
        "group_column": "city",
        "group_a": "Mumbai",
        "group_b": "Delhi",
    }))
    assert result["test"] == "t_test"
    assert "statistic" in result
    assert "p_value" in result
    assert "effect_size_cohens_d" in result
    assert result["group_a_n"] == 4
    assert result["group_b_n"] == 4


@pytest.mark.asyncio
async def test_hypothesis_mann_whitney(db_connector, rag_store):
    tool = TestHypothesisTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "test": "mann_whitney",
        "column": "amount",
        "group_column": "city",
        "group_a": "Mumbai",
        "group_b": "Delhi",
    }))
    assert result["test"] == "mann_whitney"
    assert "p_value" in result
    assert "effect_size_r" in result


@pytest.mark.asyncio
async def test_hypothesis_anova(db_connector, rag_store):
    tool = TestHypothesisTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "test": "anova",
        "column": "amount",
        "group_column": "city",
    }))
    assert result["test"] == "anova"
    assert result["num_groups"] == 3
    assert "p_value" in result
    assert "effect_size_eta_squared" in result


@pytest.mark.asyncio
async def test_hypothesis_z_proportion(db_connector, rag_store):
    tool = TestHypothesisTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "test": "z_proportion",
        "count_success": 7,
        "count_total": 10,
        "hypothesized_proportion": 0.5,
    }))
    assert result["test"] == "z_proportion"
    assert result["observed_proportion"] == 0.7
    assert "p_value" in result


@pytest.mark.asyncio
async def test_correlation_pearson(db_connector, rag_store):
    tool = ComputeCorrelationTool()
    # Need two numeric columns — use amount twice (trivial but valid)
    results = [{"x": i, "y": i * 2 + 1} for i in range(20)]
    ctx = _make_context(db_connector, rag_store, results=results)
    result = json.loads(await tool.execute(ctx, {
        "column_x": "x",
        "column_y": "y",
        "method": "pearson",
    }))
    assert result["method"] == "pearson"
    assert abs(result["correlation"] - 1.0) < 0.001  # perfect linear
    assert result["p_value"] < 0.05


@pytest.mark.asyncio
async def test_correlation_spearman(db_connector, rag_store):
    tool = ComputeCorrelationTool()
    results = [{"x": i, "y": i ** 2} for i in range(20)]
    ctx = _make_context(db_connector, rag_store, results=results)
    result = json.loads(await tool.execute(ctx, {
        "column_x": "x",
        "column_y": "y",
        "method": "spearman",
    }))
    assert result["method"] == "spearman"
    assert result["correlation"] > 0.9  # monotonic relationship


@pytest.mark.asyncio
async def test_correlation_missing_column(db_connector, rag_store):
    tool = ComputeCorrelationTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "column_x": "amount",
        "column_y": "nonexistent",
    }))
    assert "error" in result


@pytest.mark.asyncio
async def test_fit_distribution(db_connector, rag_store):
    tool = FitDistributionTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {"column": "amount"}))
    assert result["n"] == 10
    assert result["best_fit"] is not None
    assert len(result["fits"]) > 0
    # Best fit should have highest p-value
    p_values = [f["ks_p_value"] for f in result["fits"]]
    assert p_values == sorted(p_values, reverse=True)


@pytest.mark.asyncio
async def test_fit_distribution_missing_column(db_connector, rag_store):
    tool = FitDistributionTool()
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {"column": "nonexistent"}))
    assert "error" in result


@pytest.mark.asyncio
async def test_run_python_basic(db_connector, rag_store):
    tool = RunPythonTool(timeout=5)
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {"code": "print(2 + 2)"}))
    assert result["output"] == "4"


@pytest.mark.asyncio
async def test_run_python_with_df(db_connector, rag_store):
    tool = RunPythonTool(timeout=5)
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "code": "print(len(df))"
    }))
    assert result["output"] == "10"


@pytest.mark.asyncio
async def test_run_python_with_numpy(db_connector, rag_store):
    tool = RunPythonTool(timeout=5)
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "code": "print(np.mean([1, 2, 3]))"
    }))
    assert result["output"] == "2.0"


@pytest.mark.asyncio
async def test_run_python_restricted_builtins(db_connector, rag_store):
    tool = RunPythonTool(timeout=5)
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "code": "import os; print(os.listdir('.'))"
    }))
    assert "error" in result


@pytest.mark.asyncio
async def test_run_python_error_handling(db_connector, rag_store):
    tool = RunPythonTool(timeout=5)
    ctx = _make_context(db_connector, rag_store)
    result = json.loads(await tool.execute(ctx, {
        "code": "raise ValueError('test error')"
    }))
    assert "error" in result
    assert "test error" in result["error"]


@pytest.mark.asyncio
async def test_statistician_registry_has_all_tools():
    registry = statistician_registry()
    schemas = registry.get_schemas()
    names = {s["name"] for s in schemas}
    assert names == {
        "run_python", "compute_descriptive_stats", "test_hypothesis",
        "compute_correlation", "fit_distribution", "run_sql",
    }


# ---------------------------------------------------------------------------
# Statistician Loop Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_statistician_loop_basic(db_connector, rag_store, settings):
    """Test that the statistician loop runs and produces an answer."""
    mock_llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(
                id="tc1",
                name="compute_descriptive_stats",
                arguments={"column": "amount"},
            )],
        ),
        LLMResponse(
            content="The amount column has a mean of 1870 with high variance.",
            tool_calls=[],
        ),
    ])

    chunks = []
    async for chunk in statistician_loop(
        question="What is the average transaction amount?",
        analyst_results=SAMPLE_RESULTS,
        analyst_sql=SAMPLE_SQL,
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        conversation_id="test-stat-1",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "status" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "answer" in types

    # All chunks should have agent=statistician in data
    for c in chunks:
        if c.data:
            assert c.data.get("agent") == "statistician"

    answer = next(c for c in chunks if c.type == "answer")
    assert "1870" in answer.content


@pytest.mark.asyncio
async def test_statistician_loop_max_iterations(db_connector, rag_store, settings):
    """Test that the statistician stops after max iterations."""
    settings.max_statistician_iterations = 2

    infinite_tool = LLMResponse(
        content=None,
        tool_calls=[ToolCall(
            id="tc1",
            name="compute_descriptive_stats",
            arguments={"column": "amount"},
        )],
    )
    mock_llm = MockLLM([infinite_tool, infinite_tool, infinite_tool])

    chunks = []
    async for chunk in statistician_loop(
        question="test",
        analyst_results=SAMPLE_RESULTS,
        analyst_sql=SAMPLE_SQL,
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        conversation_id="test-stat-max",
    ):
        chunks.append(chunk)

    error_chunks = [c for c in chunks if c.type == "error"]
    assert len(error_chunks) == 1
    assert "maximum iterations" in error_chunks[0].content.lower()


@pytest.mark.asyncio
async def test_statistician_loop_direct_answer(db_connector, rag_store, settings):
    """Test statistician that answers immediately without tools."""
    mock_llm = MockLLM([
        LLMResponse(
            content="The data shows a clear upward trend with statistical significance.",
            tool_calls=[],
        ),
    ])

    chunks = []
    async for chunk in statistician_loop(
        question="Summarize the trends",
        analyst_results=SAMPLE_RESULTS,
        analyst_sql=SAMPLE_SQL,
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        conversation_id="test-stat-direct",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "answer" in types
    answer = next(c for c in chunks if c.type == "answer")
    assert "statistical significance" in answer.content
