from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from insightxpert.admin.dependencies import (
    AdminContext,
    assert_resource_in_scope,
    get_admin_context,
    require_admin_user,
)
from insightxpert.auth.dependencies import get_current_user
from insightxpert.auth.models import User
from insightxpert.automations.models import (
    CompileTriggerRequest,
    CreateAutomationRequest,
    CreateTriggerTemplateRequest,
    GenerateSQLRequest,
    UpdateAutomationRequest,
    UpdateTriggerTemplateRequest,
    SCHEDULE_PRESETS,
)
from insightxpert.automations.service import AutomationService
from insightxpert.db.connector import FORBIDDEN_SQL_RE

logger = logging.getLogger("insightxpert.automations")

router = APIRouter(prefix="/api/automations", tags=["automations"])
notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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


def _validate_single_sql(sql: str) -> None:
    """Validate a single SQL statement is safe and syntactically correct."""
    if FORBIDDEN_SQL_RE.search(sql):
        raise HTTPException(status_code=400, detail="SQL contains forbidden statements (only SELECT queries allowed)")

    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise HTTPException(status_code=400, detail="Multi-statement SQL is not allowed")

    # Basic syntax check: ensure it looks like a complete SELECT statement
    if not stripped.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")


def _validate_sql_queries(queries: list[str]) -> None:
    """Validate all SQL queries in a chain."""
    if not queries:
        raise HTTPException(status_code=400, detail="At least one SQL query is required")
    for i, sql in enumerate(queries):
        if not sql or not sql.strip():
            raise HTTPException(status_code=400, detail=f"SQL query at step {i + 1} is empty")
        try:
            _validate_single_sql(sql)
        except HTTPException as e:
            raise HTTPException(status_code=400, detail=f"Step {i + 1}: {e.detail}")


# ---------------------------------------------------------------------------
# SQL Generation (AI-powered)
# ---------------------------------------------------------------------------


@router.post("/generate-sql")
async def generate_sql(
    body: GenerateSQLRequest,
    request: Request,
    user: User = Depends(require_admin_user),
):
    """Generate a SQL query from a natural-language prompt using the analyst agent."""

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
# NL Trigger Compilation
# ---------------------------------------------------------------------------


@router.post("/compile-trigger")
async def compile_trigger(
    body: CompileTriggerRequest,
    request: Request,
    user: User = Depends(require_admin_user),
):
    """Compile a natural-language trigger description into a structured condition."""

    from insightxpert.automations.nl_trigger import compile_nl_trigger

    llm = request.app.state.llm
    try:
        result = await compile_nl_trigger(
            llm=llm,
            nl_text=body.nl_text,
            available_columns=body.available_columns,
        )
        return result
    except ValueError as e:
        logger.warning("Invalid automation configuration: %s", e)
        raise HTTPException(status_code=422, detail="Invalid automation configuration")


# ---------------------------------------------------------------------------
# Automation CRUD
# ---------------------------------------------------------------------------


@router.post("")
async def create_automation(
    body: CreateAutomationRequest,
    request: Request,
    user: User = Depends(require_admin_user),
):
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
    await asyncio.to_thread(_validate_sql_queries, sql_queries)

    trigger_conditions = [tc.model_dump() for tc in body.trigger_conditions]

    auto = await asyncio.to_thread(
        svc.create_automation,
        user.id,
        org_id=user.org_id,
        name=body.name,
        description=body.description,
        nl_query=body.nl_query,
        sql_queries=sql_queries,
        cron_expression=cron,
        trigger_conditions=trigger_conditions,
        source_conversation_id=body.source_conversation_id,
        source_message_id=body.source_message_id,
        workflow_graph=body.workflow_graph,
    )

    await scheduler.add_automation(auto)

    return auto


@router.get("")
async def list_automations(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    svc = _get_automation_service(request)
    if ctx.scoped_org_id is not None:
        # Org-scoped admin: see all automations in their org
        return await asyncio.to_thread(svc.list_automations, org_id=ctx.scoped_org_id, org_scoped=True)
    # Super admin: see all automations
    return await asyncio.to_thread(svc.list_automations)


@router.get("/{automation_id}")
async def get_automation(
    automation_id: str,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    auto = await asyncio.to_thread(svc.get_automation, automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(auto, user, "Automation")

    # Include recent runs
    runs = await asyncio.to_thread(svc.get_runs, automation_id, 10)
    auto["recent_runs"] = runs
    return auto


@router.put("/{automation_id}")
async def update_automation(
    automation_id: str,
    body: UpdateAutomationRequest,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    # Verify org scope before allowing update
    existing = await asyncio.to_thread(svc.get_automation, automation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(existing, user, "Automation")

    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.nl_query is not None:
        fields["nl_query"] = body.nl_query
    if body.sql_queries is not None:
        # Validate and store the updated SQL chain
        await asyncio.to_thread(_validate_sql_queries, body.sql_queries)
        fields["sql_query"] = json.dumps(body.sql_queries)
    if body.trigger_conditions is not None:
        fields["trigger_conditions"] = [tc.model_dump() for tc in body.trigger_conditions]
    if body.workflow_graph is not None:
        fields["workflow_graph"] = body.workflow_graph

    # Resolve cron
    new_cron = None
    if body.schedule_preset or body.cron_expression:
        new_cron = _resolve_cron(body)
        fields["cron_expression"] = new_cron

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await asyncio.to_thread(svc.update_automation, automation_id, **fields)

    # Reschedule if cron changed
    if new_cron:
        scheduler.reschedule_job(automation_id, new_cron)

    return result


@router.delete("/{automation_id}")
async def delete_automation(
    automation_id: str,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    existing = await asyncio.to_thread(svc.get_automation, automation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(existing, user, "Automation")

    await asyncio.to_thread(svc.delete_automation, automation_id)
    scheduler.remove_job(automation_id)
    return {"status": "ok"}


@router.patch("/{automation_id}/toggle")
async def toggle_automation(
    automation_id: str,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    existing = await asyncio.to_thread(svc.get_automation, automation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(existing, user, "Automation")

    result = await asyncio.to_thread(svc.toggle_automation, automation_id)
    assert result is not None  # existence verified above

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
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    scheduler = _get_scheduler(request)

    auto = await asyncio.to_thread(svc.get_automation, automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(auto, user, "Automation")

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
    user: User = Depends(require_admin_user),
    limit: int = Query(default=20, ge=1, le=100),
):
    svc = _get_automation_service(request)
    # Verify the automation is in scope before returning its runs
    auto = await asyncio.to_thread(svc.get_automation, automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(auto, user, "Automation")
    return await asyncio.to_thread(svc.get_runs, automation_id, limit)


@router.get("/{automation_id}/runs/{run_id}")
async def get_run(
    automation_id: str,
    run_id: str,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    auto = await asyncio.to_thread(svc.get_automation, automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    assert_resource_in_scope(auto, user, "Automation")
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
    """Get current user's own notifications."""
    svc = _get_automation_service(request)
    return await asyncio.to_thread(svc.get_notifications, user.id, unread_only)


@notifications_router.get("/all")
async def list_all_notifications(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
    unread_only: bool = Query(default=False),
):
    """Get notifications scoped by role.

    - Org admin: all notifications for users in their org (with user info).
    - Super admin: all notifications across the platform (with user info).
    """
    svc = _get_automation_service(request)
    # org_id=None → super admin (unrestricted); org_id set → org-scoped
    return await asyncio.to_thread(
        svc.get_notifications_admin, ctx.scoped_org_id, unread_only,
    )


@notifications_router.get("/count")
async def notification_count(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get current user's unread notification count."""
    svc = _get_automation_service(request)
    count = await asyncio.to_thread(svc.get_unread_count, user.id)
    return {"count": count}


@notifications_router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Mark a single notification as read (own notifications only)."""
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
    """Mark all of current user's notifications as read."""
    svc = _get_automation_service(request)
    count = await asyncio.to_thread(svc.mark_all_notifications_read, user.id)
    return {"status": "ok", "count": count}


# ---------------------------------------------------------------------------
# Trigger Template endpoints
# ---------------------------------------------------------------------------

templates_router = APIRouter(prefix="/api/trigger-templates", tags=["trigger-templates"])


@templates_router.get("")
async def list_templates(
    request: Request,
    ctx: AdminContext = Depends(get_admin_context),
):
    svc = _get_automation_service(request)
    if ctx.scoped_org_id is not None:
        return await asyncio.to_thread(svc.list_templates, org_id=ctx.scoped_org_id, org_scoped=True)
    return await asyncio.to_thread(svc.list_templates)


@templates_router.post("")
async def create_template(
    body: CreateTriggerTemplateRequest,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    conditions = [c.model_dump() for c in body.conditions]
    return await asyncio.to_thread(
        svc.create_template, user.id, body.name, body.description, conditions,
        org_id=user.org_id,
    )


@templates_router.put("/{template_id}")
async def update_template(
    template_id: str,
    body: UpdateTriggerTemplateRequest,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    existing = await asyncio.to_thread(svc.get_template, template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    assert_resource_in_scope(existing, user, "Template")
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.conditions is not None:
        fields["conditions"] = [c.model_dump() for c in body.conditions]
    result = await asyncio.to_thread(svc.update_template, template_id, **fields)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@templates_router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    request: Request,
    user: User = Depends(require_admin_user),
):
    svc = _get_automation_service(request)
    existing = await asyncio.to_thread(svc.get_template, template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    assert_resource_in_scope(existing, user, "Template")
    deleted = await asyncio.to_thread(svc.delete_template, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "ok"}
