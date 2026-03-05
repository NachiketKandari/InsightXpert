"""Tests for DB-first prompt rendering and file content helpers."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from insightxpert.auth.models import Base as AuthBase, PromptTemplate, _uuid, _utcnow
from insightxpert.prompts import render as render_prompt, get_file_content


@pytest.fixture
def auth_engine():
    """In-memory SQLAlchemy engine with auth tables created."""
    engine = create_engine("sqlite:///:memory:")
    AuthBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def seeded_engine(auth_engine):
    """Engine with a PromptTemplate row seeded for 'analyst_system'."""
    with Session(auth_engine) as session:
        session.add(
            PromptTemplate(
                id=_uuid(),
                name="analyst_system",
                content="DB prompt: Hello from the database.",
                description="test override",
                is_active=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        session.commit()
    return auth_engine


# ── render() tests ──────────────────────────────────────────────────────


def test_render_falls_back_to_file_without_engine():
    """render() without an engine should load the .j2 file from disk."""
    result = render_prompt(
        "analyst_system.j2",
        ddl="CREATE TABLE t (id INT);",
        documentation="some docs",
    )
    # The file-based template contains the InsightXpert system prompt header
    assert "InsightXpert" in result
    assert "CREATE TABLE t (id INT);" in result


def test_render_falls_back_to_file_when_not_in_db(auth_engine):
    """render() with an engine but no matching DB row should fall back to file."""
    result = render_prompt(
        "analyst_system.j2",
        engine=auth_engine,
        ddl="CREATE TABLE t (id INT);",
        documentation="some docs",
    )
    assert "InsightXpert" in result
    assert "CREATE TABLE t (id INT);" in result


def test_render_uses_db_when_available(seeded_engine):
    """render() should prefer the DB template when one exists and is active."""
    result = render_prompt("analyst_system.j2", engine=seeded_engine)
    assert result == "DB prompt: Hello from the database."


def test_render_db_template_with_variables(auth_engine):
    """DB templates with Jinja2 variables should render correctly."""
    with Session(auth_engine) as session:
        session.add(
            PromptTemplate(
                id=_uuid(),
                name="analyst_system",
                content="Hello {{ user_name }}, you have {{ count }} items.",
                is_active=True,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        session.commit()

    result = render_prompt(
        "analyst_system.j2",
        engine=auth_engine,
        user_name="Alice",
        count=42,
    )
    assert result == "Hello Alice, you have 42 items."


def test_render_skips_inactive_db_template(auth_engine):
    """An inactive DB template (is_active=False) should be ignored; file is used."""
    with Session(auth_engine) as session:
        session.add(
            PromptTemplate(
                id=_uuid(),
                name="analyst_system",
                content="THIS SHOULD NOT APPEAR",
                is_active=False,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        session.commit()

    result = render_prompt(
        "analyst_system.j2",
        engine=auth_engine,
        ddl="CREATE TABLE t (id INT);",
        documentation="some docs",
    )
    assert "THIS SHOULD NOT APPEAR" not in result
    assert "InsightXpert" in result


# ── get_file_content() tests ───────────────────────────────────────────


def test_get_file_content_success():
    """get_file_content() should return the raw file content of an existing template."""
    content = get_file_content("analyst_system.j2")
    # Raw content should contain Jinja2 markup, not rendered values
    assert "{{ ddl }}" in content
    assert "{{ documentation }}" in content


def test_get_file_content_not_found():
    """get_file_content() should raise FileNotFoundError for a missing template."""
    with pytest.raises(FileNotFoundError):
        get_file_content("nonexistent_template.j2")


def test_get_file_content_path_traversal():
    """get_file_content() should reject path-traversal attempts with ValueError."""
    with pytest.raises(ValueError, match="Invalid template name"):
        get_file_content("../../../etc/passwd")
