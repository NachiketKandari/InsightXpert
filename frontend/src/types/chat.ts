export type ChunkType =
  | "status"
  | "tool_call"
  | "sql"
  | "tool_result"
  | "answer"
  | "error";

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
  timestamp: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  isStarred: boolean;
  createdAt: number;
  updatedAt: number;
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
