"""Tests for PersistentConversationStore admin methods."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from insightxpert.auth.models import (
    Base as AuthBase,
    ConversationRecord,
    MessageRecord,
    User,
)
from insightxpert.auth.conversation_store import PersistentConversationStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine():
    """Create an in-memory SQLite engine with all auth tables."""
    eng = create_engine("sqlite:///:memory:")

    # Enable foreign key enforcement so ON DELETE CASCADE works in SQLite.
    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    AuthBase.metadata.create_all(eng)
    return eng


@pytest.fixture()
def store(engine) -> PersistentConversationStore:
    """Return a PersistentConversationStore backed by the in-memory engine."""
    return PersistentConversationStore(engine)


@pytest.fixture()
def seeded(engine, store):
    """Seed 2 users, 3 conversations (2 for user1, 1 for user2), and messages.

    Returns a dict with all created IDs for easy reference in tests.
    """
    user1_id = _uid()
    user2_id = _uid()

    conv1a_id = _uid()  # user1, conversation A
    conv1b_id = _uid()  # user1, conversation B
    conv2a_id = _uid()  # user2, conversation A

    now = _now()

    with Session(engine) as session:
        # --- users ---
        session.add(User(
            id=user1_id,
            email="user1@example.com",
            hashed_password="hashed_pw_1",
            is_active=True,
            is_admin=False,
        ))
        session.add(User(
            id=user2_id,
            email="user2@example.com",
            hashed_password="hashed_pw_2",
            is_active=True,
            is_admin=False,
        ))
        session.flush()  # flush users before adding conversations (FK)

        # --- conversations ---
        session.add(ConversationRecord(
            id=conv1a_id, user_id=user1_id, title="User1 Conv A",
            created_at=now, updated_at=now,
        ))
        session.add(ConversationRecord(
            id=conv1b_id, user_id=user1_id, title="User1 Conv B",
            created_at=now, updated_at=now,
        ))
        session.add(ConversationRecord(
            id=conv2a_id, user_id=user2_id, title="User2 Conv A",
            created_at=now, updated_at=now,
        ))
        session.flush()  # flush conversations before adding messages (FK)

        # --- messages ---
        # conv1a: 2 messages
        session.add(MessageRecord(
            id=_uid(), conversation_id=conv1a_id, role="user",
            content="Hello from user1 conv A", created_at=now,
        ))
        session.add(MessageRecord(
            id=_uid(), conversation_id=conv1a_id, role="assistant",
            content="Reply in user1 conv A", created_at=now,
        ))
        # conv1b: 1 message
        session.add(MessageRecord(
            id=_uid(), conversation_id=conv1b_id, role="user",
            content="Hello from user1 conv B", created_at=now,
        ))
        # conv2a: 3 messages
        session.add(MessageRecord(
            id=_uid(), conversation_id=conv2a_id, role="user",
            content="Hello from user2", created_at=now,
        ))
        session.add(MessageRecord(
            id=_uid(), conversation_id=conv2a_id, role="assistant",
            content="Reply to user2", created_at=now,
        ))
        session.add(MessageRecord(
            id=_uid(), conversation_id=conv2a_id, role="user",
            content="Follow-up from user2", created_at=now,
        ))

        session.commit()

    return {
        "user1_id": user1_id,
        "user2_id": user2_id,
        "conv1a_id": conv1a_id,
        "conv1b_id": conv1b_id,
        "conv2a_id": conv2a_id,
    }


# ---------------------------------------------------------------------------
# Tests: delete_conversation_admin
# ---------------------------------------------------------------------------

class TestDeleteConversationAdmin:
    def test_delete_conversation_admin_success(self, store, seeded):
        """Deleting an existing conversation returns True and removes it."""
        conv_id = seeded["conv1a_id"]

        result = store.delete_conversation_admin(conv_id)

        assert result is True
        # Verify it's actually gone
        assert store.get_conversation_admin(conv_id) is None

    def test_delete_conversation_admin_not_found(self, store, seeded):
        """Deleting a nonexistent conversation returns False."""
        result = store.delete_conversation_admin(_uid())

        assert result is False

    def test_delete_conversation_admin_cascades_messages(self, engine, store, seeded):
        """Deleting a conversation also removes its messages."""
        conv_id = seeded["conv1a_id"]

        store.delete_conversation_admin(conv_id)

        with Session(engine) as session:
            remaining = (
                session.query(MessageRecord)
                .filter(MessageRecord.conversation_id == conv_id)
                .count()
            )
        assert remaining == 0


# ---------------------------------------------------------------------------
# Tests: get_conversation_admin
# ---------------------------------------------------------------------------

class TestGetConversationAdmin:
    def test_get_conversation_admin_success(self, store, seeded):
        """Returns full conversation dict with messages."""
        conv_id = seeded["conv1a_id"]

        result = store.get_conversation_admin(conv_id)

        assert result is not None
        assert result["id"] == conv_id
        assert result["title"] == "User1 Conv A"
        assert "messages" in result
        assert len(result["messages"]) == 2
        # Verify message fields are present
        msg = result["messages"][0]
        assert "id" in msg
        assert "role" in msg
        assert "content" in msg
        assert "created_at" in msg

    def test_get_conversation_admin_not_found(self, store, seeded):
        """Returns None for a nonexistent conversation."""
        result = store.get_conversation_admin(_uid())

        assert result is None

    def test_get_conversation_admin_no_ownership_check(self, store, seeded):
        """Admin get works for any user's conversation (no ownership check)."""
        # conv1a belongs to user1; get_conversation_admin should return it
        # without needing to pass any user_id at all.
        conv_id = seeded["conv1a_id"]

        result = store.get_conversation_admin(conv_id)

        assert result is not None
        assert result["id"] == conv_id

        # For contrast, the regular get_conversation requires the owner's user_id
        # and returns None for a different user.
        wrong_user = seeded["user2_id"]
        regular_result = store.get_conversation(conv_id, wrong_user)
        assert regular_result is None

        # But admin get still works regardless
        admin_result = store.get_conversation_admin(conv_id)
        assert admin_result is not None
        assert admin_result["id"] == conv_id


# ---------------------------------------------------------------------------
# Tests: get_all_users_with_stats
# ---------------------------------------------------------------------------

class TestGetAllUsersWithStats:
    def test_get_all_users_with_stats(self, store, seeded):
        """Returns correct conversation and message counts per user."""
        results = store.get_all_users_with_stats()

        assert len(results) == 2

        stats_by_id = {r["id"]: r for r in results}

        user1 = stats_by_id[seeded["user1_id"]]
        assert user1["email"] == "user1@example.com"
        assert user1["is_active"] is True
        assert user1["conversation_count"] == 2
        assert user1["message_count"] == 3  # 2 in conv1a + 1 in conv1b

        user2 = stats_by_id[seeded["user2_id"]]
        assert user2["email"] == "user2@example.com"
        assert user2["is_active"] is True
        assert user2["conversation_count"] == 1
        assert user2["message_count"] == 3  # 3 in conv2a

    def test_get_all_users_with_stats_includes_last_active(self, store, seeded):
        """last_active is present and non-None for users with conversations."""
        results = store.get_all_users_with_stats()
        stats_by_id = {r["id"]: r for r in results}

        assert stats_by_id[seeded["user1_id"]]["last_active"] is not None
        assert stats_by_id[seeded["user2_id"]]["last_active"] is not None

    def test_get_all_users_with_stats_empty_user(self, engine, store, seeded):
        """A user with no conversations shows zero counts and None last_active."""
        user3_id = _uid()
        with Session(engine) as session:
            session.add(User(
                id=user3_id,
                email="user3@example.com",
                hashed_password="hashed_pw_3",
                is_active=True,
                is_admin=False,
            ))
            session.commit()

        results = store.get_all_users_with_stats()
        stats_by_id = {r["id"]: r for r in results}

        user3 = stats_by_id[user3_id]
        assert user3["conversation_count"] == 0
        assert user3["message_count"] == 0
        assert user3["last_active"] is None


# ---------------------------------------------------------------------------
# Tests: delete_user_conversations
# ---------------------------------------------------------------------------

class TestDeleteUserConversations:
    def test_delete_user_conversations(self, engine, store, seeded):
        """Deleting user1's conversations removes them; user2's remain."""
        user1_id = seeded["user1_id"]
        user2_id = seeded["user2_id"]

        count = store.delete_user_conversations(user1_id)

        assert count == 2  # user1 had 2 conversations

        # user1 conversations are gone
        with Session(engine) as session:
            remaining_u1 = (
                session.query(ConversationRecord)
                .filter(ConversationRecord.user_id == user1_id)
                .count()
            )
            assert remaining_u1 == 0

            # user1 messages are also gone
            remaining_msgs_u1 = (
                session.query(MessageRecord)
                .filter(
                    MessageRecord.conversation_id.in_(
                        [seeded["conv1a_id"], seeded["conv1b_id"]]
                    )
                )
                .count()
            )
            assert remaining_msgs_u1 == 0

        # user2 conversation is untouched
        with Session(engine) as session:
            remaining_u2 = (
                session.query(ConversationRecord)
                .filter(ConversationRecord.user_id == user2_id)
                .count()
            )
            assert remaining_u2 == 1

            remaining_msgs_u2 = (
                session.query(MessageRecord)
                .filter(MessageRecord.conversation_id == seeded["conv2a_id"])
                .count()
            )
            assert remaining_msgs_u2 == 3

    def test_delete_user_conversations_no_conversations(self, store, seeded):
        """Deleting conversations for a user with none returns 0."""
        count = store.delete_user_conversations(_uid())

        assert count == 0


# ---------------------------------------------------------------------------
# Tests: delete_all_conversations
# ---------------------------------------------------------------------------

class TestDeleteAllConversations:
    def test_delete_all_conversations(self, engine, store, seeded):
        """Deletes all conversations and messages, returns total count."""
        count = store.delete_all_conversations()

        assert count == 3  # 2 for user1 + 1 for user2

        with Session(engine) as session:
            assert session.query(ConversationRecord).count() == 0
            assert session.query(MessageRecord).count() == 0

    def test_delete_all_conversations_empty_db(self, store):
        """Returns 0 when there are no conversations."""
        count = store.delete_all_conversations()

        assert count == 0

    def test_delete_all_conversations_preserves_users(self, engine, store, seeded):
        """Users table is not affected by deleting all conversations."""
        store.delete_all_conversations()

        with Session(engine) as session:
            user_count = session.query(User).count()
        assert user_count == 2
