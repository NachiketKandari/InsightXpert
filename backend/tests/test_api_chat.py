"""Tests for FastAPI chat endpoints (POST /api/chat/poll, auth, agent_mode)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from .conftest import MockLLM
from insightxpert.auth.dependencies import get_current_user
from insightxpert.llm.base import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# test_chat_poll_returns_json_chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_poll_returns_json_chunks(test_app, async_client):
    """POST /api/chat/poll should return a JSON response with chunks."""
    test_app.state.llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT COUNT(*) as cnt FROM users"})],
        ),
        LLMResponse(content="There are 2 users.", tool_calls=[]),
    ])

    resp = await async_client.post("/api/chat/poll", json={"message": "How many users?"})
    assert resp.status_code == 200

    body = resp.json()
    assert "chunks" in body
    chunks = body["chunks"]
    assert len(chunks) > 0

    types = [c["type"] for c in chunks]
    assert "status" in types
    assert "answer" in types

    answer = next(c for c in chunks if c["type"] == "answer")
    assert "2 users" in answer["content"]


# ---------------------------------------------------------------------------
# test_chat_creates_conversation_in_persistent_store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_creates_conversation_in_persistent_store(test_app, async_client, persistent_conv_store, test_user):
    """After a chat poll request, a conversation should exist in the persistent store."""
    test_app.state.llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT 1 as val"})],
        ),
        LLMResponse(content="Done.", tool_calls=[]),
    ])

    resp = await async_client.post("/api/chat/poll", json={"message": "Test query"})
    assert resp.status_code == 200

    # Verify conversation was created for the test user
    convos = persistent_conv_store.get_conversations(test_user.id)
    assert len(convos) >= 1
    assert any("Test query" in c["title"] for c in convos)


# ---------------------------------------------------------------------------
# test_chat_requires_authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_requires_authentication(test_app, test_user):
    """Without the auth override, chat should return 401."""
    # Remove the auth override so real auth is used
    test_app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat/poll", json={"message": "test"})
        assert resp.status_code == 401

    # Restore override so other tests are not affected
    test_app.dependency_overrides[get_current_user] = lambda: test_user


# ---------------------------------------------------------------------------
# test_chat_with_agent_mode_analyst
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_with_agent_mode_analyst(test_app, async_client):
    """When agent_mode=analyst, no statistician chunks should appear."""
    test_app.state.llm = MockLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="tc1", name="run_sql", arguments={"sql": "SELECT * FROM users"})],
        ),
        LLMResponse(content="Here are the users.", tool_calls=[]),
    ])

    resp = await async_client.post(
        "/api/chat/poll",
        json={"message": "Show users", "agent_mode": "analyst"},
    )
    assert resp.status_code == 200

    chunks = resp.json()["chunks"]
    for chunk in chunks:
        data = chunk.get("data")
        if data:
            assert data.get("agent") != "statistician"
