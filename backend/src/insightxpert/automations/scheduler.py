from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("insightxpert.automations.scheduler")


class AutomationScheduler:
    def __init__(self, auth_engine, db) -> None:
        self._auth_engine = auth_engine
        self._db = db
        self._scheduler = AsyncIOScheduler()
        self._service = None
        self._evaluator = None

    async def start(self) -> None:
        from insightxpert.automations.service import AutomationService
        from insightxpert.automations.evaluator import TriggerEvaluator

        self._service = AutomationService(self._auth_engine)
        self._evaluator = TriggerEvaluator()

        # Load active automations
        automations = await asyncio.to_thread(self._service.get_active_automations)
        for auto in automations:
            self._add_job(auto)

        self._scheduler.start()
        logger.info("Automation scheduler started with %d active jobs", len(automations))

    def _add_job(self, automation: dict) -> None:
        try:
            trigger = CronTrigger.from_crontab(automation["cron_expression"])
            self._scheduler.add_job(
                self._execute_automation,
                trigger=trigger,
                id=automation["id"],
                args=[automation["id"]],
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.debug("Scheduled automation '%s' with cron '%s'", automation["name"], automation["cron_expression"])
        except Exception as e:
            logger.error("Failed to schedule automation '%s': %s", automation.get("name"), e)

    async def _execute_automation(self, automation_id: str) -> None:
        """Core execution loop for a single automation.

        Supports multi-query chains: executes each SQL in sequence,
        evaluates triggers against the final result only.
        """
        try:
            automation = await asyncio.to_thread(self._service.get_automation, automation_id)
            if not automation or not automation.get("is_active"):
                return

            sql_queries = automation.get("sql_queries", [])
            if not sql_queries:
                # Fallback to legacy single sql_query
                single = automation.get("sql_query", "")
                sql_queries = [single] if single else []

            if not sql_queries:
                await asyncio.to_thread(
                    self._service.create_run,
                    automation_id,
                    status="error",
                    error_message="No SQL queries configured",
                )
                await self._update_timestamps(automation_id)
                return

            start_ms = time.time()

            # Execute SQL chain — each query in sequence, keep final result
            step_results = []
            try:
                for sql in sql_queries:
                    result = await asyncio.to_thread(self._run_sql, sql)
                    step_results.append(result)
                execution_time_ms = int((time.time() - start_ms) * 1000)
            except Exception as e:
                await asyncio.to_thread(
                    self._service.create_run,
                    automation_id,
                    status="error",
                    error_message=str(e),
                )
                await self._update_timestamps(automation_id)
                return

            # Trigger evaluation uses the LAST query's result
            final_result = step_results[-1]
            rows = final_result.get("rows", [])
            row_count = len(rows)

            # Store all step results if multi-query, otherwise just the single result
            result_to_store = final_result if len(step_results) == 1 else {
                "columns": final_result.get("columns", []),
                "rows": final_result.get("rows", []),
                "step_results": step_results,
            }

            # Parse trigger conditions
            conditions_raw = automation.get("trigger_conditions", [])
            if isinstance(conditions_raw, str):
                try:
                    conditions_raw = json.loads(conditions_raw)
                except json.JSONDecodeError:
                    conditions_raw = []

            if not conditions_raw:
                await asyncio.to_thread(
                    self._service.create_run,
                    automation_id,
                    status="success",
                    result_json=json.dumps(result_to_store),
                    row_count=row_count,
                    execution_time_ms=execution_time_ms,
                )
                await self._update_timestamps(automation_id)
                return

            # Determine how many previous runs we need.
            # slope conditions need up to slope_window; change_detection needs 1.
            max_window = 1
            for cond in conditions_raw:
                if cond.get("type") == "slope":
                    w = cond.get("slope_window", 5)
                    max_window = max(max_window, w)

            runs = await asyncio.to_thread(self._service.get_runs, automation_id, max_window)

            # Extract previous results for trigger evaluation
            previous_result = None
            previous_results: list[dict] = []
            for prev_run in runs:
                prev_json = prev_run.get("result_json")
                parsed = None
                if prev_json:
                    if isinstance(prev_json, str):
                        try:
                            parsed = json.loads(prev_json)
                        except json.JSONDecodeError:
                            pass
                    else:
                        parsed = prev_json
                if parsed:
                    # For multi-step results, use the final step data
                    if "step_results" in parsed:
                        parsed = {"columns": parsed.get("columns", []), "rows": parsed.get("rows", [])}
                    previous_results.append(parsed)
                    if previous_result is None:
                        previous_result = parsed

            # Evaluate triggers
            trigger_results = self._evaluator.evaluate(
                conditions_raw, final_result, previous_result, previous_results
            )
            any_fired = self._evaluator.any_fired(trigger_results)

            status = "success" if any_fired else "no_trigger"
            run = await asyncio.to_thread(
                self._service.create_run,
                automation_id,
                status=status,
                result_json=json.dumps(result_to_store),
                row_count=row_count,
                execution_time_ms=execution_time_ms,
                triggers_fired=json.dumps(trigger_results),
            )

            if any_fired:
                fired_msgs = [r["message"] for r in trigger_results if r["fired"]]
                severity = "warning"

                await asyncio.to_thread(
                    self._service.create_notification,
                    automation["created_by"],
                    automation_id,
                    run["id"],
                    title=f"Alert: {automation['name']}",
                    message="\n".join(fired_msgs),
                    severity=severity,
                )

            await self._update_timestamps(automation_id)
            logger.info(
                "Automation '%s' executed: status=%s, rows=%d, steps=%d",
                automation["name"], status, row_count, len(sql_queries),
            )

        except Exception as e:
            logger.error("Automation execution failed for %s: %s", automation_id, e, exc_info=True)

    def _run_sql(self, sql: str) -> dict:
        """Execute SQL against the database with row limit."""
        engine = self._db.engine
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchmany(1000)]
            return {"columns": columns, "rows": rows}

    async def _update_timestamps(self, automation_id: str) -> None:
        """Update last_run_at and calculate next_run_at (fire-and-forget)."""
        try:
            now = datetime.now(timezone.utc)
            job = self._scheduler.get_job(automation_id)
            next_run = None
            if job and job.next_run_time:
                next_run = (
                    job.next_run_time.replace(tzinfo=timezone.utc)
                    if job.next_run_time.tzinfo is None
                    else job.next_run_time
                )
            asyncio.create_task(
                asyncio.to_thread(self._service.update_run_timestamps, automation_id, now, next_run)
            )
        except Exception as e:
            logger.error("Failed to update timestamps for %s: %s", automation_id, e)

    def reschedule_job(self, automation_id: str, cron_expression: str) -> None:
        try:
            trigger = CronTrigger.from_crontab(cron_expression)
            self._scheduler.reschedule_job(automation_id, trigger=trigger)
        except Exception as e:
            logger.error("Failed to reschedule %s: %s", automation_id, e)

    def remove_job(self, automation_id: str) -> None:
        try:
            self._scheduler.remove_job(automation_id)
        except Exception:
            pass  # Job may not exist

    def pause_job(self, automation_id: str) -> None:
        try:
            self._scheduler.pause_job(automation_id)
        except Exception:
            pass

    def resume_job(self, automation_id: str) -> None:
        try:
            self._scheduler.resume_job(automation_id)
        except Exception:
            pass

    async def run_now(self, automation_id: str) -> None:
        """Manually trigger an automation execution."""
        await self._execute_automation(automation_id)

    async def add_automation(self, automation: dict) -> None:
        """Add a new automation to the scheduler."""
        self._add_job(automation)

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Automation scheduler shut down")
