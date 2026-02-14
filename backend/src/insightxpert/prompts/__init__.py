"""Jinja2-based prompt template loader."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=False,  # Plain-text prompts, not HTML
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs: object) -> str:
    """Render a prompt template with the given variables.

    Usage:
        from insightxpert.prompts import render
        prompt = render("analyst_system.j2", ddl=DDL, documentation=DOCS, ...)
    """
    template = _env.get_template(template_name)
    return template.render(**kwargs).strip()
