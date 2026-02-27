from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.automations.models import (
    CreateAutomationRequest,
    GenerateSQLRequest,
    UpdateAutomationRequest,
    SCHEDULE_PRESETS,
)
from insightxpert.automations.service import AutomationService

logger = logging.getLogger("insightxpert.automations")

router = APIRouter(prefix="/api/automations", tags=["automations"])
notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# Forbidden SQL keywords for automation queries
_FORBIDDEN_SQL = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|REPLACE)\b",
    re.IGNORECASE,
)


def _get_automation_service(request: Request) -> AutomationService:
    svc = getattr(request.app.state, "automation_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Automation service not available")
    return svc


def _get_scheduler(request: Request):
    scheduler = getattr(request.app.state, "automation_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Automation scheduler not available")
    return scheduler


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


def _resolve_cron(body) -> str:
    """Resolve schedule_preset or cron_expression into a cron string."""
    if body.schedule_preset:
        cron = SCHEDULE_PRESETS.get(body.schedule_preset)
        if not cron:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown schedule preset: {body.schedule_preset}. Valid: {', '.join(SCHEDULE_PRESETS)}",
            )
        return cron
    if body.cron_expression:
        # Validate cron format
        parts = body.cron_expression.strip().split()
        if len(parts) != 5:
            raise HTTPException(status_code=400, detail="Invalid cron expression: must have exactly 5 fields")
        return body.cron_expression.strip()
    raise HTTPException(status_code=400, detail="Either schedule_preset or cron_expression is required")


def _validate_single_sql(sql: str, engine) -> None:
    """Validate a single SQL statement is safe and syntactically correct."""
    if _FORBIDDEN_SQL.search(sql):
        raise HTTPException(status_code=400, detail="SQL contains forbidden statements (only SELECT queries allowed)")

    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise HTTPException(status_code=400, detail="Multi-statement SQL is not allowed")

    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text(f"EXPLAIN {stripped}"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid SQL: {e}")


def _validate_sql_queries(queries: list[str], engine) -> None:
    """Validate all SQL queries in a chain."""
    if not queries:
        raise HTTPException(status_code=400, detail="At least one SQL query is required")
    for i, sql in enumerate(queries):
        if not sql or not sql.strip():
            raise HTTPException(status_code=400, detail=f"SQL query at step {i + 1} is empty")
        try:
            _validate_single_sql(sql, engine)
        except HTTPException as e:
            raise HTTPException(status_code=400, detail=f"Step {i + 1}: {e.detail}")


# ---------------------------------------------------------------------------
# SQL Generation (AI-powered)
# ---------------------------------------------------------------------------


@router.post("/generate-sql")
async def generate_sql(
    body: GenerateSQLRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Generate a SQL query from a natural-language prompt using the analyst agent."""
    _require_admin(user)

    from insightxpert.agents.analyst import analyst_loop

    llm = request.app.state.llm
    db = request.app.state.db
    rag = request.app.state.rag
    settings = request.app.state.settings

    executed_sql: list[str] = []
    answer = ""

    async for chunk in analyst_loop(
        question=body.prompt,
        llm=llm,
        db=db,
        rag=rag,
        config=settings,
    ):
        if chunk.type == "sql" and chunk.sql:
            executed_sql.append(chunk.sql)
        if chunk.type == "answer" and chunk.content:
            answer = chunk.content

    if not executed_sql:
        raise HTTPException(status_code=422, detail="Could not generate SQL from the given prompt")

    return {"sql": executed_sql[-1], "explanation": answer or None}


# ---------------------------------------------------------------------------
# Automation CRUD
# ---------------------------------------------------------------------------


@router.post("")
async def create_automation(
    body: CreateAutomationRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    cron = _resolve_cron(body)

    # Resolve SQL queries: prefer sql_queries, fall back to single sql_query
    sql_queries: list[str] = []
    if body.sql_queries:
        sql_queries = [q.strip() for q in body.sql_queries if q and q.strip()]
    elif body.sql_query:
        sql_queries = [body.sql_query.strip()]

    if not sql_queries:
        raise HTTPException(status_code=400, detail="At least one SQL query is required (sql_query or sql_queries)")

    # Validate all SQL queries in the chain
    db = request.app.state.db
    await asyncio.to_thread(_validate_sql_queries, sql_queries, db.engine)

    trigger_conditions = [tc.model_dump() for tc in body.trigger_conditions]

    auto = await asyncio.to_thread(
        svc.create_automation,
        user.id,
        name=body.name,
        description=body.description,
        nl_query=body.nl_query,
        sql_queries=sql_queries,
        cron_expression=cron,
        trigger_conditions=trigger_conditions,
        source_conversation_id=body.source_conversation_id,
        source_message_id=body.source_message_id,
    )

    await scheduler.add_automation(auto)

    return auto


@router.get("")
async def list_automations(
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    return await asyncio.to_thread(svc.list_automations)


@router.get("/{automation_id}")
async def get_automation(
    automation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    auto = await asyncio.to_thread(svc.get_automation, automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")

    # Include recent runs
    runs = await asyncio.to_thread(svc.get_runs, automation_id, 10)
    auto["recent_runs"] = runs
    return auto


@router.put("/{automation_id}")
async def update_automation(
    automation_id: str,
    body: UpdateAutomationRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.trigger_conditions is not None:
        fields["trigger_conditions"] = [tc.model_dump() for tc in body.trigger_conditions]

    # Resolve cron
    new_cron = None
    if body.schedule_preset or body.cron_expression:
        new_cron = _resolve_cron(body)
        fields["cron_expression"] = new_cron

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await asyncio.to_thread(svc.update_automation, automation_id, **fields)
    if not result:
        raise HTTPException(status_code=404, detail="Automation not found")

    # Reschedule if cron changed
    if new_cron:
        scheduler.reschedule_job(automation_id, new_cron)

    return result


@router.delete("/{automation_id}")
async def delete_automation(
    automation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    deleted = await asyncio.to_thread(svc.delete_automation, automation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Automation not found")

    scheduler.remove_job(automation_id)
    return {"status": "ok"}


@router.patch("/{automation_id}/toggle")
async def toggle_automation(
    automation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    result = await asyncio.to_thread(svc.toggle_automation, automation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Automation not found")

    if result["is_active"]:
        scheduler.resume_job(automation_id)
        # Re-add job in case it was fully removed
        await scheduler.add_automation(result)
    else:
        scheduler.pause_job(automation_id)

    return result


@router.post("/{automation_id}/run")
async def manual_run(
    automation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    auto = await asyncio.to_thread(svc.get_automation, automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")

    await scheduler.run_now(automation_id)

    # Return latest run
    runs = await asyncio.to_thread(svc.get_runs, automation_id, 1)
    latest_run = runs[0] if runs else None
    return {"status": "ok", "message": f"Manual run triggered for '{auto['name']}'", "run": latest_run}


# ---------------------------------------------------------------------------
# Run endpoints
# ---------------------------------------------------------------------------


@router.get("/{automation_id}/runs")
async def list_runs(
    automation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    return await asyncio.to_thread(svc.get_runs, automation_id, limit)


@router.get("/{automation_id}/runs/{run_id}")
async def get_run(
    automation_id: str,
    run_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    run = await asyncio.to_thread(svc.get_run, run_id)
    if not run or run["automation_id"] != automation_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ---------------------------------------------------------------------------
# Notification endpoints
# ---------------------------------------------------------------------------


@notifications_router.get("")
async def list_notifications(
    request: Request,
    user: User = Depends(get_current_user),
    unread_only: bool = Query(default=False),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    return await asyncio.to_thread(svc.get_notifications, user.id, unread_only)


@notifications_router.get("/count")
async def notification_count(
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    count = await asyncio.to_thread(svc.get_unread_count, user.id)
    return {"count": count}


@notifications_router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    ok = await asyncio.to_thread(svc.mark_notification_read, notification_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok"}


@notifications_router.post("/mark-all-read")
async def mark_all_read(
    request: Request,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    svc = _get_automation_service(request)
    count = await asyncio.to_thread(svc.mark_all_notifications_read, user.id)
    return {"status": "ok", "count": count}
