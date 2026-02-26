"""Clarification pre-check -- lightweight LLM call to detect ambiguous questions.

Before the analyst runs a full agentic loop, this module makes a single fast
LLM call to decide whether the user's question is clear enough to generate SQL
or whether a clarifying question should be asked first.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from insightxpert.llm.base import LLMProvider

logger = logging.getLogger("insightxpert.clarifier")

CLARIFICATION_SYSTEM_PROMPT = """You are a query pre-processor for a data analytics system backed by a SQL database.

Given the database schema (DDL), business context, and the user's question, decide:
- Is the question clear enough to generate an accurate SQL query?
- Or is it ambiguous/vague and needs a clarifying question first?

Rules:
- Only ask for clarification when the question is GENUINELY ambiguous (multiple reasonable interpretations that would produce very different SQL).
- Do NOT clarify obvious, straightforward analytical questions.
- Do NOT clarify when the user uses common data terms (e.g. "show me the data" is vague, but "average transaction amount" is clear).
- Consider conversation history -- if prior messages provide context, the current message may be clear in context.
- Clarification questions should be specific, short, and offer concrete options when possible.

Respond with ONLY a JSON object (no markdown, no explanation):
- If clear: {"action": "execute"}
- If ambiguous: {"action": "clarify", "question": "Your clarifying question here"}"""


@dataclass
class ClarificationResult:
    action: str  # "execute" or "clarify"
    question: str | None = None


async def clarification_check(
    question: str,
    ddl: str,
    documentation: str,
    llm: LLMProvider,
    history: list[dict] | None = None,
) -> ClarificationResult:
    """Run a lightweight LLM call to decide if clarification is needed.

    Returns a ClarificationResult with action="execute" or action="clarify".
    On any failure, defaults to "execute" (proceed without clarification).
    """
    user_content = f"Schema:\n{ddl}\n\nBusiness context:\n{documentation}\n\nUser question: {question}"

    messages: list[dict] = [
        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
    ]

    # Include recent history for context (last 4 messages max to keep it light)
    if history:
        for msg in history[-4:]:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

    messages.append({"role": "user", "content": user_content})

    raw = ""
    try:
        response = await llm.chat(messages, tools=None)
        raw = (response.content or "").strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        result = json.loads(raw)
        action = result.get("action", "execute")

        if action == "clarify":
            clarify_q = result.get("question", "")
            if clarify_q:
                logger.info("Clarification needed: %s", clarify_q)
                return ClarificationResult(action="clarify", question=clarify_q)

        return ClarificationResult(action="execute")

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Clarification check parse error: %s (raw: %s)", e, raw[:200])
        return ClarificationResult(action="execute")
    except Exception as e:
        logger.warning("Clarification check failed: %s", e)
        return ClarificationResult(action="execute")
