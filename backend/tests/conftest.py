from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from insightxpert.api.routes import router as api_router
from insightxpert.auth.conversation_store import PersistentConversationStore
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import Base as AuthBase, User as AuthUser, _utcnow
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMResponse
from insightxpert.memory.conversation_store import ConversationStore
from insightxpert.rag.store import VectorStore


# ---------------------------------------------------------------------------
# MockLLM
# ---------------------------------------------------------------------------


class MockLLM:
    """Mock LLM that returns predetermined responses."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._call_count = 0

    @property
    def model(self) -> str:
        return "mock"

    async def chat(self, messages, tools=None, force_tool_use=False):
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]

    async def chat_stream(self, messages, tools=None):
        resp = await self.chat(messages, tools)
        yield resp


# ---------------------------------------------------------------------------
# Existing fixtures (unchanged)
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a test SQLite DB with users + orders tables."""
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                created_at DATE
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount REAL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
        conn.execute(text("INSERT INTO users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')"))
        conn.execute(text("INSERT INTO users (id, name, email) VALUES (2, 'Bob', 'bob@example.com')"))
        conn.execute(text("INSERT INTO orders (id, user_id, amount) VALUES (1, 1, 99.99)"))
        conn.execute(text("INSERT INTO orders (id, user_id, amount) VALUES (2, 1, 49.50)"))
        conn.execute(text("INSERT INTO orders (id, user_id, amount) VALUES (3, 2, 75.00)"))
        conn.commit()
    engine.dispose()
    return url


@pytest.fixture
def db_connector(sqlite_db):
    """Return a connected DatabaseConnector."""
    db = DatabaseConnector()
    db.connect(sqlite_db)
    yield db
    db.disconnect()


@pytest.fixture
def rag_store(tmp_path):
    """Return a temporary VectorStore."""
    return VectorStore(persist_dir=str(tmp_path / "chroma_test"))


@pytest.fixture
def settings():
    return Settings(database_url="sqlite:///test.db", chroma_persist_dir="./test_chroma")


# ---------------------------------------------------------------------------
# Shared integration fixtures
# ---------------------------------------------------------------------------

TEST_USER_ID = str(uuid.uuid4())


@pytest.fixture()
def auth_engine():
    """In-memory SQLAlchemy engine with auth tables created.

    Uses StaticPool + check_same_thread=False so that sync endpoints
    (which FastAPI runs in a thread pool) share the same connection.
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
def test_user(auth_engine) -> AuthUser:
    """Seed a non-admin active user and return the User object."""
    now = _utcnow()
    user = AuthUser(
        id=TEST_USER_ID,
        email="testuser@example.com",
        hashed_password="hashed",
        is_active=True,
        is_admin=False,
        created_at=now,
        last_active=now,
    )
    with Session(auth_engine) as session:
        session.add(user)
        session.commit()
    # Return a detached object
    detached = AuthUser(
        id=TEST_USER_ID,
        email="testuser@example.com",
        hashed_password="hashed",
        is_active=True,
        is_admin=False,
        created_at=now,
        last_active=now,
    )
    return detached


@pytest.fixture()
def persistent_conv_store(auth_engine):
    """A PersistentConversationStore backed by the test engine."""
    return PersistentConversationStore(auth_engine)


@pytest.fixture()
def test_app(auth_engine, test_user, persistent_conv_store, db_connector, rag_store, settings, tmp_path):
    """Full FastAPI app with all app.state.* wired to test doubles."""
    application = FastAPI()
    application.include_router(api_router)

    application.state.auth_engine = auth_engine
    application.state.llm = MockLLM([])  # replaced per-test
    application.state.db = db_connector
    application.state.rag = rag_store
    application.state.settings = settings
    application.state.conversation_store = ConversationStore()
    application.state.persistent_conv_store = persistent_conv_store
    application.state.config_path = tmp_path / "admin_config.json"

    # Override auth to return our test user
    application.dependency_overrides[get_current_user] = lambda: test_user

    return application


@pytest.fixture()
async def async_client(test_app):
    """Async HTTP client wired to the test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
