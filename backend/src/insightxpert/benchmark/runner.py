"""Core benchmark loop: model loop -> question loop -> chunk collection."""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from insightxpert.agents.orchestrator import orchestrator_loop
from insightxpert.api.models import ChatChunk
from insightxpert.config import Settings
from insightxpert.db.connector import DatabaseConnector
from insightxpert.llm.gemini import GeminiProvider
from insightxpert.llm.ollama import OllamaProvider

from .models import BenchmarkReport, ChunkTrace, ModelRunResult, QuestionResult
from .ollama_discovery import discover_ollama_models
from .rag_isolation import cleanup_rag, create_isolated_rag, reset_qa_pairs
from .report import generate_report

logger = logging.getLogger("insightxpert.benchmark.runner")


def _chunk_to_trace(chunk: ChatChunk) -> ChunkTrace:
    return ChunkTrace(
        type=chunk.type,
        content=chunk.content,
        sql=chunk.sql,
        tool_name=chunk.tool_name,
        args=chunk.args,
        data=chunk.data,
        timestamp=chunk.timestamp,
    )


def _extract_question_result(
    index: int,
    question: str,
    chunks: list[ChatChunk],
    elapsed: float,
    timed_out: bool = False,
    exception_msg: str | None = None,
) -> QuestionResult:
    """Parse collected ChatChunks into a QuestionResult."""
    sql_generated: str | None = None
    answer: str | None = None
    errors: list[str] = []
    tool_call_count = 0
    rows_returned = 0
    sql_valid = False
    result_data: list[dict] | None = None

    if exception_msg:
        errors.append(exception_msg)

    for chunk in chunks:
        if chunk.type == "sql" and chunk.sql:
            sql_generated = chunk.sql

        elif chunk.type == "tool_call":
            tool_call_count += 1

        elif chunk.type == "tool_result" and chunk.data:
            tool_name = chunk.data.get("tool")
            raw = chunk.data.get("result", "")
            if tool_name == "run_sql" and raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        rows = parsed.get("rows", [])
                        error = parsed.get("error")
                        if error:
                            errors.append(f"SQL error: {error}")
                        else:
                            sql_valid = True
                            rows_returned = len(rows)
                            result_data = rows
                    elif isinstance(parsed, list):
                        sql_valid = True
                        rows_returned = len(parsed)
                        result_data = parsed
                except (json.JSONDecodeError, AttributeError):
                    pass

        elif chunk.type == "answer" and chunk.content:
            answer = chunk.content

        elif chunk.type == "error" and chunk.content:
            errors.append(chunk.content)

    traces = [_chunk_to_trace(c) for c in chunks]

    return QuestionResult(
        question_index=index,
        question=question,
        sql_generated=sql_generated,
        sql_valid=sql_valid,
        rows_returned=rows_returned,
        result_data=result_data,
        answer=answer,
        errors=errors,
        total_time_seconds=round(elapsed, 3),
        tool_call_count=tool_call_count,
        chunks=traces,
        has_answer=answer is not None,
        has_error=len(errors) > 0,
        timed_out=timed_out,
    )


async def _smoke_test(llm, model_name: str) -> bool:
    """Quick smoke test: ask the model to say hello."""
    try:
        response = await llm.chat([{"role": "user", "content": "Say hello"}])
        if response.content:
            logger.info("Smoke test passed for %s: %s", model_name, response.content[:80])
            return True
        logger.warning("Smoke test for %s returned empty content", model_name)
        return False
    except Exception as exc:
        logger.error("Smoke test failed for %s: %s", model_name, exc)
        return False


def _compute_aggregates(results: list[QuestionResult]) -> dict:
    """Compute aggregate metrics from a list of question results."""
    total = len(results)
    if total == 0:
        return {
            "questions_answered": 0,
            "questions_errored": 0,
            "questions_timed_out": 0,
            "success_rate": 0.0,
            "avg_time_seconds": 0.0,
            "median_time_seconds": 0.0,
            "sql_generation_rate": 0.0,
            "sql_validity_rate": 0.0,
        }

    answered = sum(1 for r in results if r.has_answer)
    errored = sum(1 for r in results if r.has_error)
    timed_out = sum(1 for r in results if r.timed_out)
    sql_generated = sum(1 for r in results if r.sql_generated)
    sql_valid = sum(1 for r in results if r.sql_valid)

    times = [r.total_time_seconds for r in results]

    return {
        "questions_answered": answered,
        "questions_errored": errored,
        "questions_timed_out": timed_out,
        "success_rate": round(answered / total * 100, 2),
        "avg_time_seconds": round(statistics.mean(times), 3),
        "median_time_seconds": round(statistics.median(times), 3),
        "sql_generation_rate": round(sql_generated / total * 100, 2),
        "sql_validity_rate": round(sql_valid / total * 100, 2) if sql_generated > 0 else 0.0,
    }


async def _run_model(
    model_name: str,
    provider: str,
    llm,
    db: DatabaseConnector,
    config: Settings,
    questions: list[str],
    timeout: int,
    agent_mode: str,
    output_dir: Path,
    parameter_size: str | None = None,
    sql_only: bool = False,
) -> ModelRunResult | None:
    """Run all questions against a single model.

    When *sql_only* is True the generator is stopped as soon as we have both
    the generated SQL and its execution result (``tool_result`` for ``run_sql``).
    This avoids waiting for the LLM to produce a final natural-language answer.
    """
    mode_label = "SQL-only" if sql_only else "full"
    logger.info("=" * 70)
    logger.info("STARTING MODEL: %s (%s) [%s]", model_name, provider, mode_label)
    logger.info("=" * 70)

    # Smoke test
    if not await _smoke_test(llm, model_name):
        logger.warning("Skipping %s — smoke test failed", model_name)
        return None

    # Create isolated RAG
    rag, temp_dir = create_isolated_rag(db)
    logger.info("Created isolated RAG for %s at %s", model_name, temp_dir)

    started_at = datetime.now(timezone.utc).isoformat()
    model_start = time.time()
    results: list[QuestionResult] = []
    consecutive_no_tool_calls = 0
    max_consecutive_no_tool_calls = 20

    try:
        for idx, question in enumerate(questions):
            q_num = idx + 1
            logger.info("[%s] Question %d/%d: %s", model_name, q_num, len(questions), question[:80])

            chunks: list[ChatChunk] = []
            q_start = time.time()
            timed_out = False
            exception_msg: str | None = None

            try:
                async def collect_chunks():
                    got_sql = False
                    got_sql_result = False
                    async for chunk in orchestrator_loop(
                        question=question,
                        llm=llm,
                        db=db,
                        rag=rag,
                        config=config,
                        agent_mode=agent_mode,
                    ):
                        chunks.append(chunk)

                        if sql_only:
                            if chunk.type == "sql" and chunk.sql:
                                got_sql = True
                            if (
                                chunk.type == "tool_result"
                                and chunk.data
                                and chunk.data.get("tool") == "run_sql"
                            ):
                                got_sql_result = True
                            # Stop once we have SQL + its execution result
                            if got_sql and got_sql_result:
                                return

                await asyncio.wait_for(collect_chunks(), timeout=timeout)

            except asyncio.TimeoutError:
                timed_out = True
                exception_msg = f"Timed out after {timeout}s"
                logger.warning("[%s] Q%d timed out after %ds", model_name, q_num, timeout)

            except Exception as exc:
                exception_msg = f"Exception: {exc}"
                logger.error("[%s] Q%d failed: %s", model_name, q_num, exc, exc_info=True)

            elapsed = time.time() - q_start
            result = _extract_question_result(idx, question, chunks, elapsed, timed_out, exception_msg)
            results.append(result)

            # Track consecutive tool call failures to detect models that can't use tools
            if result.tool_call_count == 0:
                consecutive_no_tool_calls += 1
                if consecutive_no_tool_calls >= max_consecutive_no_tool_calls:
                    logger.warning(
                        "SKIPPING %s — %d consecutive questions with no tool calls (model likely lacks tool-call support)",
                        model_name, max_consecutive_no_tool_calls,
                    )
                    break
            else:
                consecutive_no_tool_calls = 0

            # Flush auto-saved QA pairs so next question starts with only curated training data
            reset_qa_pairs(rag)

            if sql_only:
                status = "SQL_OK" if result.sql_valid else ("TIMEOUT" if result.timed_out else "NO_SQL")
            else:
                status = "OK" if result.has_answer else ("TIMEOUT" if result.timed_out else "ERROR")
            logger.info(
                "[%s] Q%d %s (%.1fs, sql=%s, rows=%d)",
                model_name, q_num, status, elapsed,
                "yes" if result.sql_generated else "no", result.rows_returned,
            )
    finally:
        cleanup_rag(temp_dir)
        logger.info("Cleaned up RAG for %s", model_name)

    finished_at = datetime.now(timezone.utc).isoformat()
    total_time = time.time() - model_start
    aggregates = _compute_aggregates(results)

    model_result = ModelRunResult(
        provider=provider,
        model=model_name,
        parameter_size=parameter_size,
        started_at=started_at,
        finished_at=finished_at,
        total_time_seconds=round(total_time, 3),
        questions_total=len(questions),
        results=results,
        **aggregates,
    )

    # Write per-model results
    model_dir = output_dir / model_name.replace(":", "-").replace("/", "-")
    model_dir.mkdir(parents=True, exist_ok=True)
    results_path = model_dir / "results.json"
    results_path.write_text(model_result.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Wrote results for %s to %s", model_name, results_path)

    return model_result


async def run_benchmark(
    questions: list[str],
    output_dir: Path,
    *,
    skip_gemini: bool = False,
    skip_ollama: bool = False,
    timeout: int = 300,
    agent_mode: str = "analyst",
    sql_only: bool = False,
) -> BenchmarkReport:
    """Run the full benchmark across all models."""
    config = Settings()
    benchmark_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    created_at = datetime.now(timezone.utc).isoformat()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect database (shared, read-only)
    db = DatabaseConnector()
    db.connect(config.database_url)
    logger.info("Connected to database: %s", config.database_url)

    model_results: list[ModelRunResult] = []

    # --- Gemini baseline ---
    if not skip_gemini:
        logger.info("Setting up Gemini baseline (%s)", config.gemini_model)
        gemini_llm = GeminiProvider(api_key=config.gemini_api_key, model=config.gemini_model)
        result = await _run_model(
            model_name=config.gemini_model,
            provider="gemini",
            llm=gemini_llm,
            db=db,
            config=config,
            questions=questions,
            timeout=timeout,
            agent_mode=agent_mode,
            output_dir=output_dir,
            sql_only=sql_only,
        )
        if result:
            model_results.append(result)

    # --- Ollama models ---
    if not skip_ollama:
        ollama_models = await discover_ollama_models(config.ollama_base_url)
        if not ollama_models:
            logger.warning("No Ollama models found at %s", config.ollama_base_url)
        else:
            for m in ollama_models:
                name = m["name"]
                logger.info("Setting up Ollama model: %s (%s)", name, m["parameter_size"])
                ollama_llm = OllamaProvider(model=name, base_url=config.ollama_base_url, timeout=float(timeout))
                result = await _run_model(
                    model_name=name,
                    provider="ollama",
                    llm=ollama_llm,
                    db=db,
                    config=config,
                    questions=questions,
                    timeout=timeout,
                    agent_mode=agent_mode,
                    output_dir=output_dir,
                    parameter_size=m["parameter_size"],
                    sql_only=sql_only,
                )
                if result:
                    model_results.append(result)

    db.disconnect()

    report = BenchmarkReport(
        benchmark_id=benchmark_id,
        created_at=created_at,
        agent_mode=agent_mode,
        sql_only=sql_only,
        questions_count=len(questions),
        models=model_results,
    )

    # Write full report
    report_path = output_dir / "report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Wrote full report to %s", report_path)

    # Generate comparison summary
    generate_report(report, output_dir)

    return report
