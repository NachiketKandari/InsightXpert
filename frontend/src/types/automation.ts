export interface TriggerCondition {
  type: "threshold" | "change_detection" | "row_count" | "column_expression" | "slope";
  column?: string | null;
  operator?: string | null;  // gt, gte, lt, lte, eq, ne
  value?: number | null;
  change_percent?: number | null;
  scope?: "any_row" | "all_rows" | null;
  slope_window?: number | null;  // number of previous runs for slope calculation
  nl_text?: string | null;  // original natural language description (if compiled from NL)
}

export interface TriggerResult {
  condition: TriggerCondition;
  fired: boolean;
  actual_value: number | null;
  message: string;
}

export interface Automation {
  id: string;
  name: string;
  description: string | null;
  nl_query: string;
  sql_query: string;
  sql_queries: string[];
  cron_expression: string;
  trigger_conditions: TriggerCondition[];
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_by: string;
  source_conversation_id: string | null;
  source_message_id: string | null;
  workflow_graph: { blocks: WorkflowBlock[]; edges: WorkflowEdge[] } | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRun {
  id: string;
  automation_id: string;
  status: "success" | "no_trigger" | "error";
  result_json: { columns: string[]; rows: Record<string, unknown>[]; step_results?: { columns: string[]; rows: Record<string, unknown>[] }[] } | null;
  row_count: number | null;
  execution_time_ms: number | null;
  triggers_fired: TriggerResult[] | null;
  error_message: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  automation_id: string | null;
  run_id: string | null;
  title: string;
  message: string;
  severity: "info" | "warning" | "critical";
  is_read: boolean;
  automation_name: string | null;
  created_at: string;
}

export interface TriggerTemplate {
  id: string;
  name: string;
  description: string | null;
  conditions: TriggerCondition[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export type SchedulePreset = "hourly" | "daily" | "weekly" | "monthly" | "custom";

// --- Workflow Builder types ---

export interface WorkflowBlock {
  id: string;
  sql: string;
  label: string;
  sourceMessageId: string | null;
  sourceMessagePreview: string | null;
  isActive: boolean;
  isEndpoint: boolean;
  resultPreview: { rowCount: number; columnCount: number; columnNames: string[] } | null;
  tables: string[];
  position: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  sourceBlockId: string;
  targetBlockId: string;
}

export interface WorkflowBuilderContext {
  conversationId: string;
  focusMessageId: string;
}

export interface AutomationContext {
  question: string;
  sqlQueries: string[];  // ordered chain of SQL queries
  columns: string[];
  rows: Record<string, unknown>[];
  conversationId: string | null;
  messageId: string | null;
}

export interface CreateAutomationPayload {
  name: string;
  description?: string;
  nl_query: string;
  sql_queries: string[];
  schedule_preset?: string;
  cron_expression?: string;
  trigger_conditions: TriggerCondition[];
  source_conversation_id?: string;
  source_message_id?: string;
  workflow_graph?: { blocks: WorkflowBlock[]; edges: WorkflowEdge[] };
}
