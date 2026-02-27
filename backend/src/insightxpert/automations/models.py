from __future__ import annotations

from pydantic import BaseModel


SCHEDULE_PRESETS = {
    "hourly": "0 * * * *",
    "daily": "0 9 * * *",
    "weekly": "0 9 * * 1",
    "monthly": "0 9 1 * *",
}


class TriggerCondition(BaseModel):
    type: str  # threshold, change_detection, row_count, column_expression, slope
    column: str | None = None
    operator: str | None = None  # gt, gte, lt, lte, eq, ne
    value: float | None = None
    change_percent: float | None = None  # for change_detection
    scope: str | None = None  # any_row, all_rows (for column_expression)
    slope_window: int | None = None  # number of previous runs for slope calculation (default 5)
    nl_text: str | None = None  # original natural language description (if compiled from NL)


class TriggerResult(BaseModel):
    condition: TriggerCondition
    fired: bool
    actual_value: float | None = None
    message: str = ""


class CreateAutomationRequest(BaseModel):
    name: str
    description: str | None = None
    nl_query: str
    sql_query: str | None = None  # single query (backward compat)
    sql_queries: list[str] | None = None  # ordered chain of SQL queries
    schedule_preset: str | None = None  # hourly, daily, weekly, monthly
    cron_expression: str | None = None  # custom cron
    trigger_conditions: list[TriggerCondition] = []
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    workflow_graph: dict | None = None  # { blocks, edges } for workflow builder


class UpdateAutomationRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    nl_query: str | None = None
    sql_queries: list[str] | None = None
    cron_expression: str | None = None
    schedule_preset: str | None = None
    trigger_conditions: list[TriggerCondition] | None = None
    workflow_graph: dict | None = None


class CompileTriggerRequest(BaseModel):
    nl_text: str
    available_columns: list[str] | None = None


class GenerateSQLRequest(BaseModel):
    prompt: str


class GenerateSQLResponse(BaseModel):
    sql: str
    explanation: str | None = None


class AutomationResponse(BaseModel):
    id: str
    name: str
    description: str | None
    nl_query: str
    sql_query: str  # kept for backward compat (first query or legacy single query)
    sql_queries: list[str]  # ordered chain of SQL queries
    cron_expression: str
    trigger_conditions: list[TriggerCondition]
    is_active: bool
    last_run_at: str | None
    next_run_at: str | None
    created_by: str
    source_conversation_id: str | None
    source_message_id: str | None
    workflow_graph: dict | None = None
    created_at: str
    updated_at: str


class AutomationRunResponse(BaseModel):
    id: str
    automation_id: str
    status: str
    result_json: dict | None = None
    row_count: int | None
    execution_time_ms: int | None
    triggers_fired: list[TriggerResult] | None = None
    error_message: str | None
    created_at: str


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    automation_id: str | None
    run_id: str | None
    title: str
    message: str
    severity: str
    is_read: bool
    automation_name: str | None = None
    created_at: str
