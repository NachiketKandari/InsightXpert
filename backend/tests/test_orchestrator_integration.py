"""Integration tests for the orchestrator pipeline (analyst -> statistician)."""

from __future__ import annotations

import json

import pytest

from .conftest import MockLLM
from insightxpert.agents.orchestrator import orchestrator_loop
from insightxpert.llm.base import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# test_orchestrator_analyst_only_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_analyst_only_mode(db_connector, rag_store, settings):
    """In analyst-only mode the orchestrator should NOT produce statistician chunks."""
    mock_llm = MockLLM([
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
        agent_mode="analyst",
    ):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "answer" in types

    # No statistician chunks should appear
    for c in chunks:
        if c.data:
            assert c.data.get("agent") != "statistician"


# ---------------------------------------------------------------------------
# test_orchestrator_auto_mode_chains_statistician
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_auto_mode_chains_statistician(db_connector, rag_store, settings):
    """In auto mode, when the analyst returns SQL results, the statistician should run."""
    # The analyst loop's first LLM call produces a tool call, then an answer.
    # After the analyst finishes, the orchestrator invokes the statistician
    # which gets its own LLM calls.
    # MockLLM delivers responses in order across both loops.
    mock_llm = MockLLM([
        # Analyst: run SQL
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT * FROM users"})],
        ),
        # Analyst: final answer
        LLMResponse(content="Here are all users.", tool_calls=[]),
        # Statistician: direct answer (no tool calls)
        LLMResponse(content="The dataset has 2 records with no notable statistical patterns.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="Show me all users",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="auto",
    ):
        chunks.append(chunk)

    # Expect chunks from both analyst and statistician
    answer_chunks = [c for c in chunks if c.type == "answer"]
    assert len(answer_chunks) == 2, f"Expected 2 answer chunks (analyst + statistician), got {len(answer_chunks)}"

    # Second answer should be from the statistician
    stat_answer = answer_chunks[1]
    assert stat_answer.data is not None
    assert stat_answer.data.get("agent") == "statistician"


# ---------------------------------------------------------------------------
# test_orchestrator_auto_mode_skips_statistician_when_no_results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_auto_mode_skips_statistician_when_no_results(db_connector, rag_store, settings):
    """When the analyst returns no SQL result rows, the statistician should be skipped."""
    mock_llm = MockLLM([
        # Analyst: run SQL that returns empty results
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT * FROM users WHERE id = 999"})],
        ),
        # Analyst: final answer
        LLMResponse(content="No users found matching the criteria.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in orchestrator_loop(
        question="Find user 999",
        llm=mock_llm,
        db=db_connector,
        rag=rag_store,
        config=settings,
        agent_mode="auto",
    ):
        chunks.append(chunk)

    # Only one answer chunk (from analyst)
    answer_chunks = [c for c in chunks if c.type == "answer"]
    assert len(answer_chunks) == 1

    # No statistician chunks at all
    for c in chunks:
        if c.data:
            assert c.data.get("agent") != "statistician"


# ---------------------------------------------------------------------------
# test_orchestrator_chunk_types_and_ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_chunk_types_and_ordering(db_connector, rag_store, settings):
    """Verify that status comes first, sql before tool_result, and answer last."""
    mock_llm = MockLLM([
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
        agent_mode="analyst",
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
