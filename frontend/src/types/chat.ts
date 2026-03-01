export type ChunkType =
  | "status"
  | "tool_call"
  | "sql"
  | "tool_result"
  | "answer"
  | "error"
  | "clarification"
  | "metrics"
  | "stats_context"
  | "insight"
  | "enrichment_trace"
  | "orchestrator_plan"
  | "agent_trace";

export interface ChatChunk {
  type: ChunkType;
  data?: Record<string, unknown> | null;
  content?: string | null;
  sql?: string | null;
  tool_name?: string | null;
  args?: Record<string, unknown> | null;
  conversation_id: string;
  timestamp: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  chunks: ChatChunk[];
  feedback?: boolean | null;
  feedbackComment?: string | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  generationTimeMs?: number | null;
  /** Wall-clock ms from when the user hit send to when all chunks arrived. Only set on freshly-streamed messages, not history loads. */
  wallTimeMs?: number | null;
  timestamp: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

export interface SearchMatchMessage {
  role: string;
  snippet: string;
  created_at: string;
}

export interface SearchResult {
  id: string;
  title: string;
  updated_at: string;
  title_match: boolean;
  matching_messages: SearchMatchMessage[];
}

export interface TraceStep {
  type: string;
  content?: string | null;
  timestamp: number;
  sql?: string | null;
  tool_name?: string | null;
  tool_args?: Record<string, unknown> | null;
  llm_reasoning?: string | null;
  result_preview?: string | null;
  result_data?: string | null;
}

export interface EnrichmentTrace {
  source_index: number;
  category: string;
  question: string;
  rationale: string;
  final_sql?: string | null;
  final_answer?: string | null;
  success: boolean;
  duration_ms?: number | null;
  steps: TraceStep[];
}

export type AgentStepStatus = "pending" | "running" | "done" | "error";

export interface AgentStep {
  id: string;
  label: string;
  status: AgentStepStatus;
  detail?: string;
  sql?: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  llmReasoning?: string;
  resultPreview?: string;
  resultData?: string;
  ragContext?: string[];
  timestamp: number;
}

export interface OrchestratorTask {
  id: string;
  agent: "sql_analyst" | "quant_analyst";
  category?: string;
  task: string;
  depends_on: string[];
}

export interface OrchestratorPlan {
  reasoning: string;
  tasks: OrchestratorTask[];
}

export interface AgentTrace {
  task_id: string;
  agent: string;
  category?: string;
  task: string;
  depends_on?: string[];
  final_sql?: string | null;
  final_answer?: string | null;
  success: boolean;
  error?: string | null;
  duration_ms?: number | null;
  steps?: TraceStep[] | null;
}
