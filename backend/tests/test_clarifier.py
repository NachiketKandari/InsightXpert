"""Tests for the clarification pre-check logic."""

from __future__ import annotations

import pytest

from insightxpert.agents.clarifier import clarification_check, ClarificationResult
from insightxpert.llm.base import LLMResponse

from .conftest import MockLLM


@pytest.mark.asyncio
async def test_clear_question_returns_execute():
    """A clear question should return action='execute'."""
    llm = MockLLM([LLMResponse(content='{"action": "execute"}')])

    result = await clarification_check(
        question="What is the average transaction amount?",
        ddl="CREATE TABLE transactions (amount_inr REAL);",
        documentation="Transactions table with amount_inr column.",
        llm=llm,
    )

    assert result.action == "execute"
    assert result.question is None


@pytest.mark.asyncio
async def test_ambiguous_question_returns_clarify():
    """An ambiguous question should return action='clarify' with a question."""
    llm = MockLLM([
        LLMResponse(content='{"action": "clarify", "question": "Which metric are you interested in: count, sum, or average?"}')
    ])

    result = await clarification_check(
        question="Show me the data",
        ddl="CREATE TABLE transactions (amount_inr REAL);",
        documentation="Transactions table.",
        llm=llm,
    )

    assert result.action == "clarify"
    assert result.question is not None
    assert "metric" in result.question.lower()


@pytest.mark.asyncio
async def test_invalid_json_defaults_to_execute():
    """If the LLM returns invalid JSON, default to execute."""
    llm = MockLLM([LLMResponse(content="I'm not sure what to do")])

    result = await clarification_check(
        question="Something vague",
        ddl="CREATE TABLE t (id INT);",
        documentation="A table.",
        llm=llm,
    )

    assert result.action == "execute"


@pytest.mark.asyncio
async def test_llm_error_defaults_to_execute():
    """If the LLM call fails, default to execute."""
    class FailingLLM:
        @property
        def model(self) -> str:
            return "failing"

        async def chat(self, messages, tools=None):
            raise RuntimeError("LLM is down")

    result = await clarification_check(
        question="Any question",
        ddl="CREATE TABLE t (id INT);",
        documentation="A table.",
        llm=FailingLLM(),
    )

    assert result.action == "execute"


@pytest.mark.asyncio
async def test_clarify_without_question_defaults_to_execute():
    """If LLM says clarify but provides no question, default to execute."""
    llm = MockLLM([LLMResponse(content='{"action": "clarify"}')])

    result = await clarification_check(
        question="Vague question",
        ddl="CREATE TABLE t (id INT);",
        documentation="A table.",
        llm=llm,
    )

    assert result.action == "execute"


@pytest.mark.asyncio
async def test_markdown_wrapped_json():
    """LLM sometimes wraps JSON in markdown code fences."""
    llm = MockLLM([LLMResponse(content='```json\n{"action": "execute"}\n```')])

    result = await clarification_check(
        question="Average amount?",
        ddl="CREATE TABLE t (amount REAL);",
        documentation="Table with amount.",
        llm=llm,
    )

    assert result.action == "execute"


@pytest.mark.asyncio
async def test_history_is_included():
    """Conversation history should be passed to the LLM."""
    calls = []

    class CapturingLLM:
        @property
        def model(self) -> str:
            return "capturing"

        async def chat(self, messages, tools=None):
            calls.append(messages)
            return LLMResponse(content='{"action": "execute"}')

    history = [
        {"role": "user", "content": "Show me food transactions"},
        {"role": "assistant", "content": "Here are the food transactions."},
    ]

    await clarification_check(
        question="Now filter by weekends",
        ddl="CREATE TABLE t (id INT);",
        documentation="Table.",
        llm=CapturingLLM(),
        history=history,
    )

    assert len(calls) == 1
    messages = calls[0]
    # system + 2 history + 1 user = 4
    assert len(messages) == 4
    assert messages[1]["content"] == "Show me food transactions"
    assert messages[2]["content"] == "Here are the food transactions."
