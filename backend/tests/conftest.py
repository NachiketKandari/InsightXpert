import pytest
from sqlalchemy import create_engine, text

from insightxpert.db.connector import DatabaseConnector
from insightxpert.rag.store import VectorStore
from insightxpert.config import Settings


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
