import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session

from insightxpert.auth.models import Base as AuthBase, PromptTemplate
from insightxpert.main import _migrate_schema, _seed_prompts


@pytest.fixture
def migration_engine(tmp_path):
    """Create a SQLite engine with minimal base tables (no new columns)."""
    db_path = tmp_path / "migrate.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                hashed_password VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE conversations (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                title VARCHAR(500) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE messages (
                id VARCHAR(36) PRIMARY KEY,
                conversation_id VARCHAR(36) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                chunks_json TEXT,
                created_at DATETIME,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE automations (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                nl_query TEXT NOT NULL,
                sql_query TEXT NOT NULL,
                cron_expression VARCHAR(100) NOT NULL,
                trigger_conditions TEXT,
                is_active BOOLEAN DEFAULT 1,
                last_run_at DATETIME,
                next_run_at DATETIME,
                created_by VARCHAR(36) NOT NULL,
                source_conversation_id VARCHAR(36),
                source_message_id VARCHAR(36),
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE automation_runs (
                id VARCHAR(36) PRIMARY KEY,
                automation_id VARCHAR(36) NOT NULL,
                status VARCHAR(20) NOT NULL,
                result_json TEXT,
                row_count INTEGER,
                execution_time_ms INTEGER,
                triggers_fired TEXT,
                error_message TEXT,
                created_at DATETIME,
                FOREIGN KEY (automation_id) REFERENCES automations(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE notifications (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                automation_id VARCHAR(36),
                run_id VARCHAR(36),
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                severity VARCHAR(20) NOT NULL,
                is_read BOOLEAN DEFAULT 0,
                created_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
    yield engine
    engine.dispose()


@pytest.fixture
def seed_engine(tmp_path):
    """Create a SQLite engine with full AuthBase schema (including prompt_templates)."""
    db_path = tmp_path / "seed.db"
    engine = create_engine(f"sqlite:///{db_path}")
    AuthBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _get_column_names(engine, table: str) -> set[str]:
    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns(table)}


def _get_table_names(engine) -> set[str]:
    insp = inspect(engine)
    return set(insp.get_table_names())


# ---------- _migrate_schema tests ----------


def test_migrate_schema_adds_columns(migration_engine):
    """New columns are added to users, conversations, and messages tables."""
    # Precondition: new columns do not exist yet
    assert "is_admin" not in _get_column_names(migration_engine, "users")
    assert "last_active" not in _get_column_names(migration_engine, "users")
    assert "is_starred" not in _get_column_names(migration_engine, "conversations")
    assert "feedback" not in _get_column_names(migration_engine, "messages")
    assert "feedback_comment" not in _get_column_names(migration_engine, "messages")

    _migrate_schema(migration_engine)

    # Postcondition: all new columns exist
    user_cols = _get_column_names(migration_engine, "users")
    assert "is_admin" in user_cols
    assert "last_active" in user_cols

    conv_cols = _get_column_names(migration_engine, "conversations")
    assert "is_starred" in conv_cols

    msg_cols = _get_column_names(migration_engine, "messages")
    assert "feedback" in msg_cols
    assert "feedback_comment" in msg_cols


def test_migrate_schema_idempotent(migration_engine):
    """Running _migrate_schema twice does not raise."""
    _migrate_schema(migration_engine)
    _migrate_schema(migration_engine)

    # Columns still present after second run
    assert "is_admin" in _get_column_names(migration_engine, "users")
    assert "is_starred" in _get_column_names(migration_engine, "conversations")
    assert "feedback" in _get_column_names(migration_engine, "messages")


def test_migrate_schema_drops_legacy_tables(migration_engine):
    """Legacy feedback and alembic_version tables are dropped if present."""
    with migration_engine.begin() as conn:
        conn.execute(text("CREATE TABLE feedback (id INTEGER PRIMARY KEY, comment TEXT)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))

    tables_before = _get_table_names(migration_engine)
    assert "feedback" in tables_before
    assert "alembic_version" in tables_before

    _migrate_schema(migration_engine)

    tables_after = _get_table_names(migration_engine)
    assert "feedback" not in tables_after
    assert "alembic_version" not in tables_after


# ---------- _seed_prompts tests ----------


def test_seed_prompts_creates_templates(seed_engine):
    """An empty prompt_templates table gets seeded with 3 templates."""
    with Session(seed_engine) as session:
        assert session.query(PromptTemplate).count() == 0

    _seed_prompts(seed_engine)

    with Session(seed_engine) as session:
        templates = session.query(PromptTemplate).all()
        assert len(templates) == 3
        names = {t.name for t in templates}
        assert names == {"analyst_system", "statistician_system", "advanced_system"}
        for t in templates:
            assert t.content  # non-empty content
            assert t.is_active is True
            assert t.description


def test_seed_prompts_idempotent(seed_engine):
    """Running _seed_prompts twice does not add duplicate rows."""
    _seed_prompts(seed_engine)
    _seed_prompts(seed_engine)

    with Session(seed_engine) as session:
        assert session.query(PromptTemplate).count() == 3


def test_seed_prompts_preserves_existing(seed_engine):
    """If a template already exists with different content, it is not overwritten,
    but missing templates are still seeded."""
    from insightxpert.auth.models import _uuid, _utcnow

    custom_content = "This is custom user-edited content."
    with Session(seed_engine) as session:
        session.add(PromptTemplate(
            id=_uuid(),
            name="analyst_system",
            content=custom_content,
            description="Custom description",
            is_active=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        ))
        session.commit()

    _seed_prompts(seed_engine)

    with Session(seed_engine) as session:
        # Custom analyst_system preserved, missing templates seeded
        assert session.query(PromptTemplate).count() == 3
        existing = session.query(PromptTemplate).filter_by(name="analyst_system").one()
        assert existing.content == custom_content
        seeded = session.query(PromptTemplate).filter_by(name="statistician_system").one()
        assert seeded.content  # non-empty, from file
        advanced = session.query(PromptTemplate).filter_by(name="advanced_system").one()
        assert advanced.content  # non-empty, from file
