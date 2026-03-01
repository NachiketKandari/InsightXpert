"""Integration tests for the orchestrator pipeline (basic + agentic flow)."""

from __future__ import annotations

import json

import pytest

from .conftest import MockLLM
from insightxpert.agents.orchestrator import orchestrator_loop
from insightxpert.llm.base import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# test_orchestrator_basic_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_basic_mode(db_connector, rag_store, settings):
    """In basic mode the orchestrator should NOT produce orchestrator chunks."""
    mock_llm = MockLLM([
        # Iteration 1: LLM answers without tool call -> guard rail forces tool use
        LLMResponse(content='{"action": "execute"}', tool_calls=[]),
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM users"})],
        ),
        LLMResponse(content="There are 2 users.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="How many users?",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="basic",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "answer" in types

    # No orchestrator-specific chunks should appear in basic mode
    assert "orchestrator_plan" not in types
    assert "agent_trace" not in types
    assert "insight" not in types


# ---------------------------------------------------------------------------
# test_orchestrator_agentic_no_enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_agentic_no_enrichment(db_connector, rag_store, settings):
    """Agentic mode where evaluator says no enrichment needed: analyst runs,
    user sees answer, evaluator returns {"enrich": false}, done."""
    mock_llm = MockLLM([
        # Phase 1: Analyst — run_sql + answer
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM users"})],
        ),
        LLMResponse(content="There are 2 users.", tool_calls=[]),
        # Phase 2: Evaluator — no enrichment
        LLMResponse(content='{"enrich": false}', tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="How many users?",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="agentic",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]

    # Analyst answer should be present (yielded directly)
    assert "answer" in types

    # Evaluator status should appear
    status_contents = [c.content for c in chunks if c.type == "status"]
    assert any("deeper analysis" in (s or "").lower() for s in status_contents)

    # No enrichment-related chunks
    assert "orchestrator_plan" not in types
    assert "agent_trace" not in types
    assert "insight" not in types


# ---------------------------------------------------------------------------
# test_orchestrator_agentic_with_enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_agentic_with_enrichment(db_connector, rag_store, settings):
    """Agentic mode with enrichment: analyst runs first, evaluator plans tasks,
    DAG executes, synthesis produces insight. User sees both answer and insight."""
    enrichment_json = json.dumps({
        "enrich": True,
        "reasoning": "Additional segment comparison needed.",
        "tasks": [
            {"id": "B", "agent": "sql_analyst", "task": "Count users by name", "depends_on": []},
        ],
    })

    mock_llm = MockLLM([
        # Phase 1: Analyst — run_sql + answer
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM users"})],
        ),
        LLMResponse(content="There are 2 users.", tool_calls=[]),
        # Phase 2: Evaluator — enrichment needed
        LLMResponse(content=enrichment_json, tool_calls=[]),
        # Phase 3: Enrichment task B (sql_analyst)
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc2", name="run_sql", arguments={"sql": "SELECT name, COUNT(*) as cnt FROM users GROUP BY name"})],
        ),
        LLMResponse(content="Alice has 1 record, Bob has 1 record.", tool_calls=[]),
        # Phase 4: Response generator (synthesizer)
        LLMResponse(content="There are 2 users [[1]]. Alice and Bob each have 1 record [[2]].", tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="How many users?",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="agentic",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]

    # Phase 1: analyst answer should appear (yielded directly)
    assert "answer" in types

    # Phase 3: enrichment plan + agent trace
    assert "orchestrator_plan" in types
    assert "agent_trace" in types

    # Phase 5: enrichment trace with correct source indices
    et_chunks = [c for c in chunks if c.type == "enrichment_trace"]
    assert len(et_chunks) >= 2
    source_indices = [c.data["source_index"] for c in et_chunks]
    assert 1 in source_indices  # original analyst
    assert 2 in source_indices  # enrichment task B

    # Phase 4: insight should appear after answer
    assert "insight" in types
    answer_idx = types.index("answer")
    insight_idx = types.index("insight")
    assert answer_idx < insight_idx, "answer must appear before insight"

    # Insight should contain synthesized text
    insight_chunk = next(c for c in chunks if c.type == "insight")
    assert "2 users" in insight_chunk.content

    # Plan chunk should show enrichment tasks
    plan_chunk = next(c for c in chunks if c.type == "orchestrator_plan")
    assert plan_chunk.data is not None
    tasks = plan_chunk.data.get("tasks", [])
    assert len(tasks) == 1
    assert tasks[0]["id"] == "B"


# ---------------------------------------------------------------------------
# test_orchestrator_agentic_analyst_failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_agentic_analyst_failure(db_connector, rag_store, settings):
    """When analyst errors in agentic mode, no enrichment should happen."""
    mock_llm = MockLLM([
        # Analyst: returns error
        LLMResponse(content="I cannot understand this question.", tool_calls=[]),
    ])

    # Create settings with just 1 iteration so analyst exhausts quickly
    short_settings = settings.model_copy(update={"max_agent_iterations": 1})

    chunks = []
    async for chunk in orchestrator_loop(
        question="???",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=short_settings,
        agent_mode="agentic",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]

    # Should have error from analyst, but no enrichment
    assert "orchestrator_plan" not in types
    assert "insight" not in types


# ---------------------------------------------------------------------------
# test_orchestrator_legacy_mode_maps_to_agentic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_legacy_mode_maps_to_agentic(db_connector, rag_store, settings):
    """Legacy modes (auto, statistician, advanced) should map to agentic."""
    mock_llm = MockLLM([
        # Phase 1: Analyst
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) FROM users"})],
        ),
        LLMResponse(content="2 users.", tool_calls=[]),
        # Phase 2: Evaluator — no enrichment
        LLMResponse(content='{"enrich": false}', tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="Count users",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="auto",  # legacy mode
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    # Should have used agentic pipeline (analyst ran first, evaluator checked)
    assert "answer" in types
    # Evaluator decided no enrichment, so no orchestrator_plan
    status_contents = [c.content for c in chunks if c.type == "status"]
    assert any("deeper analysis" in (s or "").lower() for s in status_contents)


# ---------------------------------------------------------------------------
# test_orchestrator_legacy_analyst_maps_to_basic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_legacy_analyst_maps_to_basic(db_connector, rag_store, settings):
    """Legacy agent_mode='analyst' should map to 'basic'."""
    mock_llm = MockLLM([
        LLMResponse(content='{"action": "execute"}', tool_calls=[]),
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) FROM users"})],
        ),
        LLMResponse(content="2 users.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="Count users",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="analyst",  # legacy mode
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "answer" in types
    # No orchestrator/agentic chunks
    assert "orchestrator_plan" not in types
    assert "insight" not in types


# ---------------------------------------------------------------------------
# test_orchestrator_chunk_types_and_ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_chunk_types_and_ordering(db_connector, rag_store, settings):
    """Verify that status comes first, sql before tool_result, and answer last."""
    mock_llm = MockLLM([
        # Iteration 1: LLM answers without tool call -> guard rail forces tool use
        LLMResponse(content='{"action": "execute"}', tool_calls=[]),
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM orders"})],
        ),
        LLMResponse(content="There are 3 orders.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="How many orders?",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="basic",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]

    # First chunk should be a status
    assert types[0] == "status"

    # Answer should be the last chunk
    assert types[-1] == "answer"

    # sql should appear before tool_result
    sql_idx = types.index("sql")
    result_idx = types.index("tool_result")
    assert sql_idx < result_idx, "sql chunk should come before tool_result chunk"
