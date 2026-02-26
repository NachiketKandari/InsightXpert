"""Jinja2-based prompt template loader with DB-first fallback to file."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

_PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=False,  # Plain-text prompts, not HTML
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

_sandbox_env = SandboxedEnvironment(
    autoescape=False,
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

logger = logging.getLogger("insightxpert.prompts")


def _get_from_db(engine, prompt_name: str) -> str | None:
    """Try to load a prompt template from the database."""
    try:
        from insightxpert.auth.models import PromptTemplate

        with Session(engine) as session:
            template = (
                session.query(PromptTemplate)
                .filter(PromptTemplate.name == prompt_name, PromptTemplate.is_active.is_(True))
                .first()
            )
            if template:
                return template.content
    except (OperationalError, ProgrammingError):
        # Table may not exist yet during startup
        logger.debug("DB prompt lookup failed for '%s', falling back to file", prompt_name)
    except Exception:
        logger.warning("Unexpected error loading prompt '%s' from DB", prompt_name, exc_info=True)
    return None


def render(template_name: str, *, engine=None, **kwargs: object) -> str:
    """Render a prompt template. Checks DB first, falls back to Jinja2 file.

    Usage:
        from insightxpert.prompts import render
        prompt = render("analyst_system.j2", engine=engine, ddl=DDL, ...)
    """
    if engine:
        prompt_name = template_name.replace(".j2", "")
        db_content = _get_from_db(engine, prompt_name)
        if db_content:
            logger.debug("Using DB template for '%s'", prompt_name)
            tmpl = _sandbox_env.from_string(db_content)
            return tmpl.render(**kwargs).strip()

    template = _env.get_template(template_name)
    return template.render(**kwargs).strip()


def get_file_content(template_name: str) -> str:
    """Read the raw content of a file-based template (for seeding/reset)."""
    path = (_PROMPTS_DIR / template_name).resolve()
    if not path.is_relative_to(_PROMPTS_DIR.resolve()):
        raise ValueError(f"Invalid template name: {template_name}")
    return path.read_text()
