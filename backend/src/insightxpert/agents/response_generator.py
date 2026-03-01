"""Response generator — synthesizes all sub-task results into a cited response.

Single LLM call (no tools) that combines evidence from all completed sub-tasks
into a leadership-grade response with source citations matching task IDs.

When ``original_analyst`` is provided (analyst-first flow), Source [1] is always
the original analyst's answer, and additional enrichment tasks start at [2].
"""

from __future__ import annotations

import logging

from insightxpert.agents.common import build_evidence_blocks
from insightxpert.agents.dag_executor import (
    OriginalAnalystResult,
    OrchestratorPlan,
    SubTaskResult,
)
from insightxpert.llm.base import LLMProvider
from insightxpert.prompts import render as render_prompt

logger = logging.getLogger("insightxpert.response_generator")


async def generate_response(
    question: str,
    plan: OrchestratorPlan,
    results: dict[str, SubTaskResult],
    llm: LLMProvider,
    *,
    ddl: str,
    documentation: str,
    original_analyst: OriginalAnalystResult | None = None,
) -> str:
    """Synthesize all sub-task results into a cited response via one LLM call.

    When *original_analyst* is provided, it becomes Source [1] and the
    additional enrichment tasks are numbered starting at [2].

    On failure, returns a formatted concatenation of individual agent answers.
    """
    evidence_data = build_evidence_blocks(question, plan, results, original_analyst)

    plan_reasoning = plan.reasoning
    if original_analyst:
        plan_reasoning = (
            f"Source [1] is the original analyst's direct answer to the user's question. "
            f"Additional sources provide enrichment analysis. {plan_reasoning}"
        )

    system_prompt = render_prompt(
        "response_generator.j2",
        ddl=ddl,
        documentation=documentation,
        question=question,
        evidence_data=evidence_data,
        plan_reasoning=plan_reasoning,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Synthesize all the evidence into a comprehensive, cited response."},
    ]

    try:
        response = await llm.chat(messages, tools=None)
        return response.content or _fallback_answer(plan, results, original_analyst)
    except Exception as exc:
        logger.error("Response generation failed: %s", exc, exc_info=True)
        return _fallback_answer(plan, results, original_analyst)


def _fallback_answer(
    plan: OrchestratorPlan,
    results: dict[str, SubTaskResult],
    original_analyst: OriginalAnalystResult | None = None,
) -> str:
    """Concatenate individual agent answers as a fallback."""
    parts: list[str] = []

    if original_analyst and original_analyst.answer:
        parts.append(f"**Original Analysis**\n\n{original_analyst.answer}")

    for task in plan.tasks:
        result = results.get(task.id)
        if result and result.success and result.answer:
            parts.append(f"**[{task.id}] {task.task}**\n\n{result.answer}")

    if parts:
        return "\n\n---\n\n".join(parts)
    return "Unable to generate a response. Please try rephrasing your question."
