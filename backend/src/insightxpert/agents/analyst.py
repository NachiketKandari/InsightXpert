from __future__ import annotations

import logging
import re
import time
import uuid
from typing import AsyncGenerator

from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.base import LLMProvider
from insightxpert.rag.store import VectorStore
from insightxpert.training.documentation import DOCUMENTATION
from insightxpert.training.schema import DDL

from .tool_base import ToolContext, ToolRegistry
from .tools import default_registry

logger = logging.getLogger("insightxpert.analyst")

MAX_ITERATIONS = 10

SYSTEM_PROMPT_TEMPLATE = """\
You are **InsightXpert**, an AI data analyst built for the Techfest IIT Bombay \
Leadership Analytics Challenge. You translate natural-language questions about \
Indian digital payment transactions into accurate SQL, execute the queries, and \
deliver clear, evidence-backed answers for non-technical leadership audiences.

## Database Schema

{ddl}

## Business Context

{documentation}

## Tools Available

You have three tools:
- **run_sql** — execute a SELECT query against the SQLite database
- **get_schema** — inspect table DDL (use if unsure about columns)
- **search_similar** — search the knowledge base for similar past queries, DDL, or docs

## Rules

1. **SELECT only** — never write INSERT, UPDATE, DELETE, DROP, or any DDL.
2. **NULL semantics** — `merchant_category` is NULL for P2P transactions; \
`receiver_age_group` is NULL for non-P2P. Exclude NULLs from aggregations, \
do not impute.
3. **fraud_flag** means "flagged for review", NOT confirmed fraud. Always say \
"flagged for review" in your response.
4. **ROUND()** all decimal results to 2 decimal places.
5. **Correlation != causation** — surface patterns, never assert causal claims.
6. **Small samples** — if a result is based on fewer than 500 rows, flag it \
explicitly (e.g., "Note: based on N records").
7. Always execute the SQL with run_sql before answering — never guess results.

## Response Structure

Structure every answer with these layers:
1. **Direct Answer** (1-2 sentences in plain business language)
2. **Supporting Evidence** (key numbers, comparisons, rankings from the data)
3. **Data Provenance** (row count, scope, time range of the underlying data)
4. **Caveats** (small samples, NULL exclusions, synthetic data disclaimers — when relevant)
5. **Follow-up Suggestions** (1-2 natural next questions the user might ask)

{rag_context}"""


def _build_system_prompt(
    similar_qa: list[dict],
    relevant_ddl: list[dict],
    relevant_docs: list[dict],
    relevant_findings: list[dict],
) -> str:
    rag_parts: list[str] = []

    if relevant_ddl:
        rag_parts.append("## Introspected Schema (from DB)")
        for item in relevant_ddl:
            rag_parts.append(item["document"])

    if similar_qa:
        rag_parts.append("## Similar Past Queries (for reference)")
        for item in similar_qa:
            rag_parts.append(item["document"])

    if relevant_docs:
        rag_parts.append("## Additional Documentation")
        for item in relevant_docs:
            rag_parts.append(item["document"])

    if relevant_findings:
        rag_parts.append("## Anomaly Findings (background analysis)")
        for item in relevant_findings:
            rag_parts.append(item["document"])

    rag_context = "\n".join(rag_parts) if rag_parts else ""

    return SYSTEM_PROMPT_TEMPLATE.format(
        ddl=DDL,
        documentation=DOCUMENTATION,
        rag_context=rag_context,
    )


def _extract_sql_from_messages(messages: list[dict]) -> str | None:
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                if tc.name == "run_sql":
                    return tc.arguments.get("sql")
        content = msg.get("content", "")
        if isinstance(content, str):
            match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                return match.group(1).strip()
    return None


async def analyst_loop(
    question: str,
    llm: LLMProvider,
    db: DatabaseConnector,
    rag: VectorStore,
    config: Settings,
    conversation_id: str | None = None,
    history: list[dict] | None = None,
    tool_registry: ToolRegistry | None = None,
) -> AsyncGenerator[ChatChunk, None]:
    cid = conversation_id or str(uuid.uuid4())[:12]
    loop_start = time.time()

    # Build tool registry and context
    if tool_registry is None:
        tool_registry = default_registry()
    tool_context = ToolContext(db=db, rag=rag, row_limit=config.sql_row_limit)

    logger.info("=" * 60)
    logger.info("NEW QUESTION [%s]: %s", cid, question)
    logger.info("=" * 60)

    yield ChatChunk(
        type="status",
        content="Searching knowledge base for context...",
        conversation_id=cid,
        timestamp=time.time(),
    )

    rag_start = time.time()
    similar_qa = rag.search_qa(question, n=5)
    relevant_ddl = rag.search_ddl(question, n=3)
    relevant_docs = rag.search_docs(question, n=3)
    relevant_findings = rag.search_findings(question, n=2)
    rag_ms = (time.time() - rag_start) * 1000

    logger.info(
        "RAG retrieval (%.0fms): qa=%d ddl=%d docs=%d findings=%d",
        rag_ms, len(similar_qa), len(relevant_ddl), len(relevant_docs), len(relevant_findings),
    )
    if similar_qa:
        for i, qa in enumerate(similar_qa):
            logger.debug("  qa[%d] dist=%.3f: %s", i, qa["distance"], qa["document"][:100])

    system_prompt = _build_system_prompt(
        similar_qa, relevant_ddl, relevant_docs, relevant_findings,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    # Inject conversation history for multi-turn context
    if history:
        messages.extend(history)
        logger.info("Injected %d history messages for conversation %s", len(history), cid)

    messages.append({"role": "user", "content": question})

    max_iter = config.max_agent_iterations or MAX_ITERATIONS

    for iteration in range(max_iter):
        logger.info("--- Iteration %d/%d ---", iteration + 1, max_iter)

        llm_start = time.time()
        response = await llm.chat(messages, tools=tool_registry.get_schemas())
        llm_ms = (time.time() - llm_start) * 1000

        if response.tool_calls:
            tool_names = [tc.name for tc in response.tool_calls]
            logger.info("LLM response (%.0fms): tool_calls=%s", llm_ms, tool_names)
            if response.content:
                logger.debug("LLM thinking: %s", response.content[:200])

            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            })

            for tc in response.tool_calls:
                yield ChatChunk(
                    type="tool_call",
                    content=f"Calling {tc.name}...",
                    sql=tc.arguments.get("sql") if tc.name == "run_sql" else None,
                    tool_name=tc.name,
                    args=tc.arguments,
                    conversation_id=cid,
                    timestamp=time.time(),
                )

                if tc.name == "run_sql" and tc.arguments.get("sql"):
                    logger.info("SQL: %s", tc.arguments["sql"])
                    yield ChatChunk(
                        type="sql",
                        sql=tc.arguments["sql"],
                        conversation_id=cid,
                        timestamp=time.time(),
                    )

                tool_start = time.time()
                result = await tool_registry.execute(
                    tc.name, tc.arguments, tool_context,
                )
                tool_ms = (time.time() - tool_start) * 1000
                logger.info("Tool %s completed (%.0fms): %s", tc.name, tool_ms, result[:200])

                messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                })

                yield ChatChunk(
                    type="tool_result",
                    data={"tool": tc.name, "result": result},
                    tool_name=tc.name,
                    conversation_id=cid,
                    timestamp=time.time(),
                )
        else:
            total_ms = (time.time() - loop_start) * 1000
            answer_preview = (response.content or "")[:200]
            logger.info("LLM final answer (%.0fms): %s...", llm_ms, answer_preview)
            logger.info(
                "DONE [%s] total=%.0fms iterations=%d",
                cid, total_ms, iteration + 1,
            )

            yield ChatChunk(
                type="answer",
                content=response.content,
                conversation_id=cid,
                timestamp=time.time(),
            )

            sql = _extract_sql_from_messages(messages)
            if sql:
                try:
                    rag.add_qa_pair(question, sql)
                    logger.debug("Auto-saved QA pair to RAG")
                except Exception:
                    pass
            break
    else:
        total_ms = (time.time() - loop_start) * 1000
        logger.warning(
            "EXHAUSTED [%s] max iterations=%d total=%.0fms",
            cid, max_iter, total_ms,
        )
        yield ChatChunk(
            type="error",
            content=f"Agent reached maximum iterations ({max_iter}) without producing a final answer.",
            conversation_id=cid,
            timestamp=time.time(),
        )
