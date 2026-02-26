"""Jinja2-based prompt template loader with DB-first, file-fallback resolution.

This module implements a two-tier prompt resolution strategy:

1. **Database lookup** (preferred) -- If a SQLAlchemy ``engine`` is provided,
   the module first queries the ``prompt_templates`` table for an active row
   whose ``name`` matches the template (minus the ``.j2`` extension).  This
   allows operators to hot-swap prompts at runtime without redeploying.

2. **File-system fallback** -- When no DB override is found (or no engine is
   supplied), the module falls back to the ``.j2`` Jinja2 template files
   co-located in this package directory.

All Jinja2 templates are rendered as **plain text** (``autoescape=False``)
because the output is injected into LLM system prompts, not into HTML pages.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

_PROMPTS_DIR = Path(__file__).parent

# Standard (trusted) Jinja2 environment for rendering file-based templates.
# autoescape is disabled because these templates produce plain-text prompts
# destined for an LLM, not HTML.  HTML escaping would corrupt Markdown
# formatting and SQL examples embedded in the prompt.
_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=False,  # Plain-text prompts, not HTML
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Sandboxed Jinja2 environment for rendering DB-sourced templates.
# Templates stored in the database are treated as *untrusted* input because
# they can be modified by any user with admin access to the prompt_templates
# table.  The SandboxedEnvironment restricts attribute access and disallows
# dangerous operations (e.g. calling dunder methods, accessing private attrs)
# to mitigate server-side template injection (SSTI) risks.
_sandbox_env = SandboxedEnvironment(
    autoescape=False,
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

logger = logging.getLogger("insightxpert.prompts")


def _get_from_db(engine, prompt_name: str) -> str | None:
    """Try to load an active prompt template from the database.

    Queries the ``PromptTemplate`` model for a row matching *prompt_name*
    with ``is_active=True``.  Returns the raw Jinja2 template string if
    found, or ``None`` on any failure.

    Gracefully handles ``OperationalError`` and ``ProgrammingError`` because
    the ``prompt_templates`` table may not yet exist during initial startup
    or migration.  In that case the caller silently falls back to the
    file-based template.

    Args:
        engine: A SQLAlchemy engine instance used to open a session.
        prompt_name: Logical prompt name (e.g. ``"analyst_system"``),
            without the ``.j2`` extension.

    Returns:
        The template content string, or ``None`` if not found / on error.
    """
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
    """Render a prompt template with DB-first, file-fallback resolution.

    Resolution order:
        1. If *engine* is provided, strip the ``.j2`` suffix and query the
           ``prompt_templates`` DB table for an active override.  DB-sourced
           templates are rendered in the **sandboxed** Jinja2 environment to
           guard against SSTI.
        2. If no DB hit (or *engine* is ``None``), load the ``.j2`` file from
           the ``prompts/`` package directory using the trusted environment.

    Common template variables (passed via **kwargs):
        - ``ddl`` -- CREATE TABLE statement for the transactions table.
        - ``documentation`` -- Business-context documentation string.
        - ``similar_qa`` -- List of RAG-retrieved similar Q&A pairs.
        - ``relevant_findings`` -- List of RAG-retrieved anomaly findings.

    Args:
        template_name: Filename of the Jinja2 template (e.g.
            ``"analyst_system.j2"``).
        engine: Optional SQLAlchemy engine for DB prompt lookup.
        **kwargs: Template variables forwarded to ``Jinja2.render()``.

    Returns:
        The fully rendered prompt string, with leading/trailing whitespace
        stripped.
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
    """Read the raw (un-rendered) content of a file-based template.

    This is used by the seed/reset admin endpoint to populate the
    ``prompt_templates`` DB table with the canonical on-disk templates.

    A path-traversal guard ensures the resolved path stays within the
    ``prompts/`` package directory.  Any ``template_name`` containing ``..``
    segments that would escape the directory will raise ``ValueError``.

    Args:
        template_name: Filename relative to the prompts directory
            (e.g. ``"analyst_system.j2"``).

    Returns:
        The raw template content as a string.

    Raises:
        ValueError: If the resolved path escapes the prompts directory.
    """
    path = (_PROMPTS_DIR / template_name).resolve()
    if not path.is_relative_to(_PROMPTS_DIR.resolve()):
        raise ValueError(f"Invalid template name: {template_name}")
    return path.read_text()
