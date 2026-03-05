"""Tests for the admin API routes (insightxpert.admin.routes)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from insightxpert.admin.routes import router as admin_router
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import (
    Base as AuthBase,
    ConversationRecord,
    MessageRecord,
    PromptTemplate,
    User,
    _utcnow,
    _uuid,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_USER_ID = str(uuid.uuid4())
OTHER_USER_ID = str(uuid.uuid4())


def _make_admin_user() -> User:
    """Create a detached User ORM object representing an admin."""
    user = User(
        id=ADMIN_USER_ID,
        email="admin@test.com",
        hashed_password="hashed",
        is_active=True,
        is_admin=True,
        created_at=_utcnow(),
        last_active=_utcnow(),
    )
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def auth_engine():
    """In-memory SQLAlchemy engine with auth tables created.

    Uses SQLite in-memory with StaticPool for fast isolated ORM tests.
    SQLAlchemy ORM is dialect-agnostic so this works for testing
    application logic even though production uses PostgreSQL.
    """
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AuthBase.metadata.create_all(engine)
    return engine


@pytest.fixture()
def persistent_conv_store(auth_engine):
    """A PersistentConversationStore backed by the test engine."""
    return PersistentConversationStore(auth_engine)


@pytest.fixture()
def rag_mock():
    """Mock RAG object with flush_qa_pairs."""
    mock = MagicMock()
    mock.flush_qa_pairs.return_value = 0
    return mock


@pytest.fixture()
def app(auth_engine, persistent_conv_store, rag_mock):
    """Create a minimal FastAPI app with the admin router and overrides."""
    application = FastAPI()
    application.include_router(admin_router)

    # Wire up app.state dependencies used by the routes
    application.state.auth_engine = auth_engine
    application.state.persistent_conv_store = persistent_conv_store
    application.state.rag = rag_mock

    # Seed the admin user in the DB so _resolve_admin_scope finds it
    with Session(auth_engine) as session:
        session.add(User(
            id=ADMIN_USER_ID,
            email="admin@test.com",
            hashed_password="hashed",
            is_active=True,
            is_admin=True,
            created_at=_utcnow(),
            last_active=_utcnow(),
        ))
        session.commit()

    # Override auth dependency to return a mock admin user
    application.dependency_overrides[get_current_user] = _make_admin_user

    return application


@pytest.fixture()
async def client(app):
    """Async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_users(engine) -> tuple[str, str]:
    """Insert two users and return (admin_id, other_id)."""
    now = _utcnow()
    with Session(engine) as session:
        admin = User(
            id=ADMIN_USER_ID,
            email="admin@test.com",
            hashed_password="hashed",
            is_active=True,
            is_admin=True,
            created_at=now,
            last_active=now,
        )
        other = User(
            id=OTHER_USER_ID,
            email="other@example.com",
            hashed_password="hashed",
            is_active=True,
            is_admin=False,
            created_at=now,
            last_active=now,
        )
        session.merge(admin)
        session.merge(other)
        session.commit()
    return ADMIN_USER_ID, OTHER_USER_ID


def _seed_conversation(engine, user_id: str, *, title: str = "Test Chat") -> str:
    """Insert a conversation and return its id."""
    conv_id = _uuid()
    now = _utcnow()
    with Session(engine) as session:
        session.add(
            ConversationRecord(
                id=conv_id,
                user_id=user_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    return conv_id


def _seed_message(engine, conversation_id: str, *, role: str = "user", content: str = "Hello") -> str:
    """Insert a message and return its id."""
    msg_id = _uuid()
    now = _utcnow()
    with Session(engine) as session:
        session.add(
            MessageRecord(
                id=msg_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=now,
            )
        )
        session.commit()
    return msg_id


def _seed_prompt(engine, *, name: str = "analyst_system", content: str = "You are an analyst.") -> str:
    """Insert a prompt template and return its id."""
    prompt_id = _uuid()
    now = _utcnow()
    with Session(engine) as session:
        session.add(
            PromptTemplate(
                id=prompt_id,
                name=name,
                content=content,
                description=f"Description for {name}",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    return prompt_id


# ---------------------------------------------------------------------------
# User management tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users(client, auth_engine):
    _seed_users(auth_engine)
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    emails = {u["email"] for u in data["users"]}
    assert "admin@test.com" in emails
    assert "other@example.com" in emails
    # Each user entry has the expected stat keys
    for u in data["users"]:
        assert "conversation_count" in u
        assert "message_count" in u


# ---------------------------------------------------------------------------
# Conversation management tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_user_conversations(client, auth_engine):
    _seed_users(auth_engine)
    conv_id = _seed_conversation(auth_engine, OTHER_USER_ID, title="Chat A")
    _seed_message(auth_engine, conv_id, content="Hi there")

    resp = await client.get(f"/api/admin/users/{OTHER_USER_ID}/conversations")
    assert resp.status_code == 200
    convos = resp.json()["conversations"]
    assert len(convos) >= 1
    assert any(c["title"] == "Chat A" for c in convos)


@pytest.mark.asyncio
async def test_get_conversation_detail(client, auth_engine):
    _seed_users(auth_engine)
    conv_id = _seed_conversation(auth_engine, OTHER_USER_ID, title="Detail Chat")
    _seed_message(auth_engine, conv_id, role="user", content="question")
    _seed_message(auth_engine, conv_id, role="assistant", content="answer")

    resp = await client.get(f"/api/admin/conversations/{conv_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == conv_id
    assert body["title"] == "Detail Chat"
    assert len(body["messages"]) == 2
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant"]


@pytest.mark.asyncio
async def test_get_conversation_not_found(client, auth_engine):
    _seed_users(auth_engine)
    fake_id = _uuid()
    resp = await client.get(f"/api/admin/conversations/{fake_id}")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_conversation(client, auth_engine):
    _seed_users(auth_engine)
    conv_id = _seed_conversation(auth_engine, OTHER_USER_ID)
    _seed_message(auth_engine, conv_id, content="to be deleted")

    resp = await client.delete(f"/api/admin/conversations/{conv_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify it is actually gone
    resp2 = await client.get(f"/api/admin/conversations/{conv_id}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_not_found(client, auth_engine):
    _seed_users(auth_engine)
    fake_id = _uuid()
    resp = await client.delete(f"/api/admin/conversations/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_conversations(client, auth_engine):
    _seed_users(auth_engine)
    _seed_conversation(auth_engine, OTHER_USER_ID, title="C1")
    _seed_conversation(auth_engine, OTHER_USER_ID, title="C2")

    resp = await client.delete(f"/api/admin/conversations/user/{OTHER_USER_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["deleted_count"] == 2

    # Verify no conversations remain for that user
    resp2 = await client.get(f"/api/admin/users/{OTHER_USER_ID}/conversations")
    assert resp2.json()["conversations"] == []


@pytest.mark.asyncio
async def test_delete_all_conversations(client, auth_engine):
    _seed_users(auth_engine)
    _seed_conversation(auth_engine, ADMIN_USER_ID, title="Admin Chat")
    _seed_conversation(auth_engine, OTHER_USER_ID, title="User Chat")

    resp = await client.delete("/api/admin/conversations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["deleted_count"] == 2

    # Both users should have zero conversations now
    r1 = await client.get(f"/api/admin/users/{ADMIN_USER_ID}/conversations")
    r2 = await client.get(f"/api/admin/users/{OTHER_USER_ID}/conversations")
    assert r1.json()["conversations"] == []
    assert r2.json()["conversations"] == []


# ---------------------------------------------------------------------------
# Prompt management tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_prompts(client, auth_engine):
    _seed_prompt(auth_engine, name="alpha", content="Alpha content")
    _seed_prompt(auth_engine, name="beta", content="Beta content")

    resp = await client.get("/api/admin/prompts")
    assert resp.status_code == 200
    prompts = resp.json()["prompts"]
    names = {p["name"] for p in prompts}
    assert "alpha" in names
    assert "beta" in names


@pytest.mark.asyncio
async def test_get_prompt(client, auth_engine):
    _seed_prompt(auth_engine, name="my_prompt", content="prompt body")

    resp = await client.get("/api/admin/prompts/my_prompt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "my_prompt"
    assert body["content"] == "prompt body"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_get_prompt_not_found(client):
    resp = await client.get("/api/admin/prompts/nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upsert_prompt_create(client, auth_engine):
    resp = await client.put(
        "/api/admin/prompts/new_prompt",
        json={"content": "brand new prompt", "description": "desc", "is_active": True},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new_prompt"

    # Verify it was persisted
    resp2 = await client.get("/api/admin/prompts/new_prompt")
    assert resp2.status_code == 200
    assert resp2.json()["content"] == "brand new prompt"


@pytest.mark.asyncio
async def test_upsert_prompt_update(client, auth_engine):
    _seed_prompt(auth_engine, name="existing", content="old content")

    resp = await client.put(
        "/api/admin/prompts/existing",
        json={"content": "updated content", "description": "updated desc", "is_active": False},
    )
    assert resp.status_code == 200

    resp2 = await client.get("/api/admin/prompts/existing")
    assert resp2.status_code == 200
    assert resp2.json()["content"] == "updated content"
    assert resp2.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_prompt(client, auth_engine):
    _seed_prompt(auth_engine, name="to_delete", content="doomed")

    resp = await client.delete("/api/admin/prompts/to_delete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Confirm it is gone
    resp2 = await client.get("/api/admin/prompts/to_delete")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_prompt_not_found(client):
    resp = await client.delete("/api/admin/prompts/ghost")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reset_prompt_existing(client, auth_engine):
    """Reset an existing prompt to its file default."""
    _seed_prompt(auth_engine, name="analyst_system", content="custom override")

    with patch("insightxpert.admin.routes.get_file_content", return_value="file default content"):
        resp = await client.post("/api/admin/prompts/analyst_system/reset")

    assert resp.status_code == 200
    assert resp.json()["name"] == "analyst_system"

    # Verify content was replaced with file default
    resp2 = await client.get("/api/admin/prompts/analyst_system")
    assert resp2.json()["content"] == "file default content"


@pytest.mark.asyncio
async def test_reset_prompt_no_file_template(client):
    """Reset should 404 when there is no file template for the given name."""
    with patch("insightxpert.admin.routes.get_file_content", side_effect=FileNotFoundError):
        resp = await client.post("/api/admin/prompts/nonexistent/reset")

    assert resp.status_code == 404
    assert "no file template" in resp.json()["detail"].lower()
