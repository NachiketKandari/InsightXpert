"""Compile a natural-language trigger description into a structured TriggerCondition."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("insightxpert.automations.nl_trigger")

_SYSTEM_PROMPT = """\
You are a trigger condition compiler. The user describes a trigger condition in plain English.
You must output ONLY a JSON object (no markdown, no explanation) representing one trigger condition.

The JSON must have a "type" field that is one of:
- "threshold" — compare a single value against a threshold
- "row_count" — compare the number of result rows
- "change_detection" — fire when value changes by N% from previous run
- "column_expression" — check a column value across rows
- "slope" — compute rate of change across recent runs

Fields per type:
- threshold: { "type": "threshold", "column": "<col_name or null>", "operator": "<gt|gte|lt|lte|eq|ne>", "value": <number> }
- row_count: { "type": "row_count", "operator": "<gt|gte|lt|lte|eq|ne>", "value": <number> }
- change_detection: { "type": "change_detection", "column": "<col_name or null>", "change_percent": <number> }
- column_expression: { "type": "column_expression", "column": "<col_name>", "operator": "<gt|gte|lt|lte|eq|ne>", "value": <number>, "scope": "<any_row|all_rows>" }
- slope: { "type": "slope", "column": "<col_name or null>", "operator": "<gt|gte|lt|lte|eq|ne>", "value": <number>, "slope_window": <int, default 5> }

Available columns: {columns}

Output ONLY the JSON object. No markdown fences, no text before or after.
"""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```\w*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


async def compile_nl_trigger(
    llm,
    nl_text: str,
    available_columns: list[str] | None = None,
) -> dict:
    """Send the NL trigger description to the LLM and return a structured condition dict.

    Args:
        llm: The LLM service instance (must support .generate or similar).
        nl_text: Natural language trigger description.
        available_columns: Column names available in the query result.

    Returns:
        A dict with at least a "type" key matching one of the 5 trigger types.

    Raises:
        ValueError: If the LLM output is not valid JSON or has an invalid type.
    """
    columns_str = ", ".join(available_columns) if available_columns else "(not specified)"
    system_prompt = _SYSTEM_PROMPT.format(columns=columns_str)

    response_text = await _call_llm(llm, system_prompt, nl_text)

    # Parse the response
    cleaned = _strip_code_fences(response_text)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON: %s", cleaned[:200])
        raise ValueError(f"LLM output is not valid JSON: {e}") from e

    # Validate type
    valid_types = {"threshold", "row_count", "change_detection", "column_expression", "slope"}
    if result.get("type") not in valid_types:
        raise ValueError(f"Invalid trigger type: {result.get('type')}. Must be one of: {valid_types}")

    # Preserve the original NL text
    result["nl_text"] = nl_text

    return result


async def _call_llm(llm, system_prompt: str, user_message: str) -> str:
    """Call the LLM to generate a response. Handles both sync and async interfaces."""
    import asyncio

    prompt = f"{system_prompt}\n\nUser trigger description: {user_message}"

    # Try using the underlying model directly (Gemini)
    for attr in ("_model", "model"):
        model = getattr(llm, attr, None)
        if model and hasattr(model, "generate_content"):
            response = await asyncio.to_thread(
                model.generate_content,
                [{"role": "user", "parts": [{"text": prompt}]}],
            )
            return response.text

    # Fallback: use the generate method if available
    if hasattr(llm, "generate"):
        result = await asyncio.to_thread(llm.generate, prompt)
        return str(result)

    raise ValueError("Could not find a suitable LLM generation method")
