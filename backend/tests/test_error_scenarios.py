"""Tests for error handling across agents and API endpoints."""

from __future__ import annotations

import pytest

from .conftest import MockLLM
from insightxpert.agents.analyst import analyst_loop
from insightxpert.llm.base import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# test_sql_syntax_error_returns_error_in_tool_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_syntax_error_returns_error_in_tool_result(db_connector, rag_store, settings):
    """A bad SQL query should produce an error in the tool result, then the agent answers."""
    mock_llm = MockLLM([
        # First call: bad SQL
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECTT INVALID SYNTAX"})],
        ),
        # Second call: the LLM sees the error and provides an answer
        LLMResponse(content="I encountered a SQL error. Please rephrase.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in analyst_loop("Bad query", mock_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    # There should be a tool_result with an error from the bad SQL
    tool_results = [c for c in chunks if c.type == "tool_result"]
    assert len(tool_results) >= 1
    first_result = tool_results[0]
    assert first_result.data is not None
    result_str = first_result.data.get("result", "")
    assert "error" in result_str.lower()

    # The agent should still produce a final answer
    answer_chunks = [c for c in chunks if c.type == "answer"]
    assert len(answer_chunks) == 1


# ---------------------------------------------------------------------------
# test_sql_syntax_error_recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_syntax_error_recovery(db_connector, rag_store, settings):
    """After a SQL error, the LLM retries with valid SQL and succeeds."""
    mock_llm = MockLLM([
        # First call: bad SQL
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "INVALID SQL"})],
        ),
        # Second call: LLM sees error, retries with valid SQL
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc2", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM users"})],
        ),
        # Third call: final answer
        LLMResponse(content="There are 2 users.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in analyst_loop("Count users", mock_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    # Should have two tool_result chunks (one error, one success)
    tool_results = [c for c in chunks if c.type == "tool_result"]
    assert len(tool_results) == 2

    # First result has an error
    first_result_str = tool_results[0].data.get("result", "")
    assert "error" in first_result_str.lower()

    # Second result has valid rows
    second_result_str = tool_results[1].data.get("result", "")
    assert "rows" in second_result_str.lower()

    # Final answer should exist
    answer_chunks = [c for c in chunks if c.type == "answer"]
    assert len(answer_chunks) == 1
    assert "2 users" in answer_chunks[0].content


# ---------------------------------------------------------------------------
# test_llm_failure_returns_error_chunk
# ---------------------------------------------------------------------------


class FailingLLM:
    """An LLM mock that raises ConnectionError."""

    @property
    def model(self) -> str:
        return "failing-mock"

    async def chat(self, messages, tools=None, force_tool_use=False):
        raise ConnectionError("LLM service unavailable")


@pytest.mark.asyncio
async def test_llm_failure_returns_error_chunk(db_connector, rag_store, settings):
    """When the LLM raises an exception, an error chunk should be emitted."""
    failing_llm = FailingLLM()

    chunks = []
    async for chunk in analyst_loop("test", failing_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    error_chunks = [c for c in chunks if c.type == "error"]
    assert len(error_chunks) == 1
    assert "LLM service unavailable" in error_chunks[0].content


# ---------------------------------------------------------------------------
# test_unknown_tool_call_returns_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_call_returns_error(db_connector, rag_store, settings):
    """When the LLM calls a nonexistent tool, an error should be in the tool result."""
    mock_llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="nonexistent_tool", arguments={"foo": "bar"})],
        ),
        LLMResponse(content="I could not use that tool.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in analyst_loop("test", mock_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    tool_results = [c for c in chunks if c.type == "tool_result"]
    assert len(tool_results) >= 1
    result_str = tool_results[0].data.get("result", "")
    assert "unknown tool" in result_str.lower()


# ---------------------------------------------------------------------------
# test_sql_execute_endpoint_rejects_write_queries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_execute_endpoint_rejects_write_queries(test_app, async_client):
    """POST /api/sql/execute should reject DROP TABLE and other write operations."""
    resp = await async_client.post("/api/sql/execute", json={"sql": "DROP TABLE users"})
    assert resp.status_code == 403
    assert "write operations" in resp.json()["detail"].lower() or "blocked" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# test_sql_execute_endpoint_rejects_empty_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_execute_endpoint_rejects_empty_query(test_app, async_client):
    """POST /api/sql/execute should reject empty SQL strings."""
    resp = await async_client.post("/api/sql/execute", json={"sql": ""})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()

    # Also test whitespace-only
    resp2 = await async_client.post("/api/sql/execute", json={"sql": "   "})
    assert resp2.status_code == 400
