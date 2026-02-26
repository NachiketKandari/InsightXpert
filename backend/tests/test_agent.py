"""Tests for the analyst agent loop using a mock LLM."""

from __future__ import annotations

import pytest

from .conftest import MockLLM
from insightxpert.agents.analyst import analyst_loop
from insightxpert.llm.base import LLMResponse, ToolCall


@pytest.mark.asyncio
async def test_agent_loop_simple_query(db_connector, rag_store, settings):
    """Test that the agent can execute a SQL query and return an answer."""
    mock_llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM users"})],
        ),
        LLMResponse(content="There are 2 users in the database.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in analyst_loop("How many users?", mock_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "status" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "answer" in types

    answer = next(c for c in chunks if c.type == "answer")
    assert "2 users" in answer.content


@pytest.mark.asyncio
async def test_agent_loop_emits_sql_chunk(db_connector, rag_store, settings):
    """Test that a SQL chunk is emitted when run_sql is called."""
    mock_llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT * FROM users"})],
        ),
        LLMResponse(content="Here are the users.", tool_calls=[]),
    ])

    chunks = []
    async for chunk in analyst_loop("Show me all users", mock_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    sql_chunks = [c for c in chunks if c.type == "sql"]
    assert len(sql_chunks) == 1
    assert "SELECT * FROM users" in sql_chunks[0].sql


@pytest.mark.asyncio
async def test_agent_loop_max_iterations(db_connector, rag_store, settings):
    """Test that the agent stops after max iterations."""
    settings.max_agent_iterations = 2

    infinite_tool = LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="tc1", name="get_schema", arguments={})],
    )
    mock_llm = MockLLM([infinite_tool, infinite_tool, infinite_tool])

    chunks = []
    async for chunk in analyst_loop("test", mock_llm, db_connector, rag_store, settings):
        chunks.append(chunk)

    error_chunks = [c for c in chunks if c.type == "error"]
    assert len(error_chunks) == 1
    assert "maximum iterations" in error_chunks[0].content.lower()


@pytest.mark.asyncio
async def test_insightxpert_training(rag_store):
    """Verify all training data loads into RAG correctly."""
    from insightxpert.training.trainer import Trainer
    from insightxpert.training.queries import EXAMPLE_QUERIES

    trainer = Trainer(rag_store)
    count = trainer.train_insightxpert(db=None)

    # 1 DDL + 1 documentation + 12 Q&A pairs = 14
    assert count == 14

    # Verify Q&A pairs are searchable
    results = rag_store.search_qa("average transaction amount", n=3)
    assert len(results) >= 1

    # Verify documentation is searchable
    results = rag_store.search_docs("fraud flag", n=1)
    assert len(results) == 1
    assert "flagged for review" in results[0]["document"].lower()

    # Verify DDL is searchable
    results = rag_store.search_ddl("transactions table", n=1)
    assert len(results) == 1

    # Verify all 12 Q&A pairs loaded
    all_qa = rag_store.search_qa("transaction", n=20)
    assert len(all_qa) == len(EXAMPLE_QUERIES)
