"""Tests for the PersistentConversationStore CRUD operations."""

from __future__ import annotations

import json

import pytest

from insightxpert.auth.conversation_store import PersistentConversationStore


# ---------------------------------------------------------------------------
# test_create_save_load_conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_save_load_conversation(persistent_conv_store, test_user):
    """Full CRUD cycle: create conversation, save messages, load them back."""
    store: PersistentConversationStore = persistent_conv_store
    user_id = test_user.id

    # Create
    convo = store.create_conversation(user_id, "My Test Chat")
    assert convo["id"]
    assert convo["title"] == "My Test Chat"
    cid = convo["id"]

    # Save messages
    msg1_id = store.save_message(cid, user_id, "user", "Hello, world!")
    msg2_id = store.save_message(cid, user_id, "assistant", "Hi there!")
    assert msg1_id
    assert msg2_id

    # Load
    loaded = store.get_conversation(cid, user_id)
    assert loaded is not None
    assert loaded["id"] == cid
    assert loaded["title"] == "My Test Chat"
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["role"] == "user"
    assert loaded["messages"][0]["content"] == "Hello, world!"
    assert loaded["messages"][1]["role"] == "assistant"
    assert loaded["messages"][1]["content"] == "Hi there!"

    # Delete
    deleted = store.delete_conversation(cid, user_id)
    assert deleted is True

    # Verify deleted
    assert store.get_conversation(cid, user_id) is None


# ---------------------------------------------------------------------------
# test_multi_turn_conversation_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_turn_conversation_history(persistent_conv_store, test_user):
    """Simulate 3 rounds of user/assistant messages and verify ordering."""
    store: PersistentConversationStore = persistent_conv_store
    user_id = test_user.id

    convo = store.create_conversation(user_id, "Multi-turn Chat")
    cid = convo["id"]

    turns = [
        ("user", "What is the total revenue?"),
        ("assistant", "The total revenue is $224.49"),
        ("user", "Break it down by user"),
        ("assistant", "Alice: $149.49, Bob: $75.00"),
        ("user", "Who spent the most?"),
        ("assistant", "Alice spent the most at $149.49"),
    ]

    for role, content in turns:
        store.save_message(cid, user_id, role, content)

    loaded = store.get_conversation(cid, user_id)
    assert loaded is not None
    assert len(loaded["messages"]) == 6

    # Verify ordering is preserved
    for i, (role, content) in enumerate(turns):
        assert loaded["messages"][i]["role"] == role
        assert loaded["messages"][i]["content"] == content


# ---------------------------------------------------------------------------
# test_conversation_with_chunks_json_roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_with_chunks_json_roundtrip(persistent_conv_store, test_user):
    """Verify chunks_json is preserved through save and load."""
    store: PersistentConversationStore = persistent_conv_store
    user_id = test_user.id

    convo = store.create_conversation(user_id, "Chunks Test")
    cid = convo["id"]

    chunks_data = [
        {"type": "status", "content": "Analyzing..."},
        {"type": "sql", "sql": "SELECT 1"},
        {"type": "answer", "content": "Done."},
    ]
    chunks_json = json.dumps(chunks_data)

    store.save_message(cid, user_id, "user", "test question")
    store.save_message(cid, user_id, "assistant", "test answer", chunks_json)

    loaded = store.get_conversation(cid, user_id)
    assert loaded is not None
    assert len(loaded["messages"]) == 2

    assistant_msg = loaded["messages"][1]
    assert assistant_msg["chunks_json"] is not None
    parsed = json.loads(assistant_msg["chunks_json"])
    assert len(parsed) == 3
    assert parsed[0]["type"] == "status"
    assert parsed[1]["type"] == "sql"
    assert parsed[2]["type"] == "answer"
