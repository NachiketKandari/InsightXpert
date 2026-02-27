import { create } from "zustand";
import { apiCall, apiFetch } from "@/lib/api";
import type {
  Automation,
  AutomationRun,
  AutomationContext,
  CreateAutomationPayload,
  TriggerCondition,
  WorkflowBlock,
  WorkflowEdge,
  WorkflowBuilderContext,
} from "@/types/automation";
import type { Message } from "@/types/chat";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _blockCounter = 0;
function nextBlockId() {
  return `block-${++_blockCounter}`;
}

/**
 * Kahn's algorithm — topological sort over active, connected blocks.
 * Returns the ordered list of SQL strings for the automation payload.
 */
function topologicalSort(blocks: WorkflowBlock[], edges: WorkflowEdge[]): string[] {
  const activeIds = new Set(blocks.filter((b) => b.isActive).map((b) => b.id));
  const activeEdges = edges.filter(
    (e) => activeIds.has(e.sourceBlockId) && activeIds.has(e.targetBlockId),
  );

  const inDegree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const id of activeIds) {
    inDegree.set(id, 0);
    adj.set(id, []);
  }
  for (const e of activeEdges) {
    adj.get(e.sourceBlockId)!.push(e.targetBlockId);
    inDegree.set(e.targetBlockId, (inDegree.get(e.targetBlockId) ?? 0) + 1);
  }

  const queue: string[] = [];
  for (const [id, deg] of inDegree) {
    if (deg === 0) queue.push(id);
  }

  const sorted: string[] = [];
  while (queue.length > 0) {
    const node = queue.shift()!;
    sorted.push(node);
    for (const neighbor of adj.get(node) ?? []) {
      const newDeg = (inDegree.get(neighbor) ?? 1) - 1;
      inDegree.set(neighbor, newDeg);
      if (newDeg === 0) queue.push(neighbor);
    }
  }

  // Map sorted block IDs → SQL
  const blockMap = new Map(blocks.map((b) => [b.id, b]));
  return sorted.map((id) => blockMap.get(id)!.sql);
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface AutomationState {
  automations: Automation[];
  isLoading: boolean;
  error: string | null;

  // Legacy modal state (kept for backward compat during transition)
  automationModalOpen: boolean;
  automationModalContext: AutomationContext | null;

  // Workflow builder state
  workflowBuilderOpen: boolean;
  workflowBuilderContext: WorkflowBuilderContext | null;
  workflowBlocks: WorkflowBlock[];
  workflowEdges: WorkflowEdge[];
  isGeneratingSQL: boolean;

  // Automation CRUD
  fetchAutomations: () => Promise<void>;
  createAutomation: (payload: CreateAutomationPayload) => Promise<Automation | null>;
  updateAutomation: (id: string, payload: Partial<CreateAutomationPayload>) => Promise<Automation | null>;
  deleteAutomation: (id: string) => Promise<boolean>;
  toggleAutomation: (id: string) => Promise<Automation | null>;
  runNow: (id: string) => Promise<{ status: string; message: string; run: AutomationRun | null } | null>;
  fetchRunHistory: (id: string, limit?: number) => Promise<AutomationRun[]>;

  // Legacy modal (kept so existing admin/automations page still works)
  openAutomationModal: (context: AutomationContext) => void;
  closeAutomationModal: () => void;

  // Workflow builder actions
  openWorkflowBuilder: (context: WorkflowBuilderContext) => void;
  closeWorkflowBuilder: () => void;
  initBlocksFromConversation: (messages: Message[], focusMessageId: string) => void;
  addBlock: (block: WorkflowBlock) => void;
  updateBlock: (id: string, updates: Partial<WorkflowBlock>) => void;
  removeBlock: (id: string) => void;
  toggleBlockActive: (id: string) => void;
  setEndpointBlock: (id: string) => void;
  updateBlockPosition: (id: string, position: { x: number; y: number }) => void;
  addEdge: (edge: WorkflowEdge) => void;
  removeEdge: (id: string) => void;
  generateSQL: (prompt: string) => Promise<void>;
  saveWorkflowAsAutomation: (meta: {
    name: string;
    description?: string;
    schedulePreset?: string;
    cronExpression?: string;
    triggerConditions: TriggerCondition[];
  }) => Promise<Automation | null>;
}

export const useAutomationStore = create<AutomationState>((set, get) => ({
  automations: [],
  isLoading: false,
  error: null,
  automationModalOpen: false,
  automationModalContext: null,

  workflowBuilderOpen: false,
  workflowBuilderContext: null,
  workflowBlocks: [],
  workflowEdges: [],
  isGeneratingSQL: false,

  // ---------------------------------------------------------------------------
  // Automation CRUD (unchanged)
  // ---------------------------------------------------------------------------

  fetchAutomations: async () => {
    set({ isLoading: true, error: null });
    const data = await apiCall<Automation[]>("/api/automations");
    set({ automations: data ?? [], isLoading: false });
  },

  createAutomation: async (payload) => {
    const data = await apiCall<Automation>("/api/automations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (data) {
      set((s) => ({ automations: [data, ...s.automations] }));
    }
    return data;
  },

  updateAutomation: async (id, payload) => {
    const data = await apiCall<Automation>(`/api/automations/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    if (data) {
      set((s) => ({
        automations: s.automations.map((a) => (a.id === id ? data : a)),
      }));
    }
    return data;
  },

  deleteAutomation: async (id) => {
    const res = await apiFetch(`/api/automations/${id}`, { method: "DELETE" });
    if (res.ok) {
      set((s) => ({
        automations: s.automations.filter((a) => a.id !== id),
      }));
      return true;
    }
    return false;
  },

  toggleAutomation: async (id) => {
    const data = await apiCall<Automation>(`/api/automations/${id}/toggle`, {
      method: "PATCH",
    });
    if (data) {
      set((s) => ({
        automations: s.automations.map((a) => (a.id === id ? data : a)),
      }));
    }
    return data;
  },

  runNow: async (id) => {
    return await apiCall<{ status: string; message: string; run: AutomationRun | null }>(
      `/api/automations/${id}/run`,
      { method: "POST" },
    );
  },

  fetchRunHistory: async (id, limit = 20) => {
    return (await apiCall<AutomationRun[]>(`/api/automations/${id}/runs?limit=${limit}`)) ?? [];
  },

  // Legacy modal
  openAutomationModal: (context) => set({ automationModalOpen: true, automationModalContext: context }),
  closeAutomationModal: () => set({ automationModalOpen: false, automationModalContext: null }),

  // ---------------------------------------------------------------------------
  // Workflow builder
  // ---------------------------------------------------------------------------

  openWorkflowBuilder: (context) =>
    set({
      workflowBuilderOpen: true,
      workflowBuilderContext: context,
      workflowBlocks: [],
      workflowEdges: [],
    }),

  closeWorkflowBuilder: () =>
    set({
      workflowBuilderOpen: false,
      workflowBuilderContext: null,
      workflowBlocks: [],
      workflowEdges: [],
    }),

  initBlocksFromConversation: (messages, focusMessageId) => {
    const blocks: WorkflowBlock[] = [];
    let y = 0;

    // Walk assistant messages, extract SQL chunks, pair with preceding user question
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role !== "assistant") continue;

      // Find the preceding user question
      let userQuestion = "";
      for (let j = i - 1; j >= 0; j--) {
        if (messages[j].role === "user") {
          userQuestion = messages[j].content;
          break;
        }
      }

      const sqlChunks = msg.chunks.filter((c) => c.type === "sql" && c.sql);
      const toolResultChunks = msg.chunks.filter((c) => c.type === "tool_result");

      for (let k = 0; k < sqlChunks.length; k++) {
        const sql = sqlChunks[k].sql!;
        const toolResult = toolResultChunks[k];
        const resultData = toolResult?.data as
          | { result?: string }
          | undefined;

        // Try to extract row/column counts from the tool result
        let resultPreview: { rowCount: number; columnCount: number } | null = null;
        if (resultData?.result) {
          try {
            const parsed = JSON.parse(resultData.result as string);
            if (parsed.columns && parsed.rows) {
              resultPreview = {
                rowCount: parsed.rows.length,
                columnCount: parsed.columns.length,
              };
            }
          } catch {
            // not parseable, skip
          }
        }

        blocks.push({
          id: nextBlockId(),
          sql,
          label: userQuestion
            ? `${userQuestion.slice(0, 60)}${userQuestion.length > 60 ? "..." : ""}`
            : `SQL Query ${blocks.length + 1}`,
          sourceMessageId: msg.id,
          sourceMessagePreview: userQuestion || null,
          isActive: true,
          isEndpoint: false,
          resultPreview,
          position: { x: 300, y },
        });
        y += 200;
      }
    }

    // Auto-mark the last SQL block from focusMessageId as endpoint
    const focusBlocks = blocks.filter((b) => b.sourceMessageId === focusMessageId);
    if (focusBlocks.length > 0) {
      focusBlocks[focusBlocks.length - 1].isEndpoint = true;
    } else if (blocks.length > 0) {
      blocks[blocks.length - 1].isEndpoint = true;
    }

    set({ workflowBlocks: blocks });
  },

  addBlock: (block) => set((s) => ({ workflowBlocks: [...s.workflowBlocks, block] })),

  updateBlock: (id, updates) =>
    set((s) => ({
      workflowBlocks: s.workflowBlocks.map((b) => (b.id === id ? { ...b, ...updates } : b)),
    })),

  removeBlock: (id) =>
    set((s) => ({
      workflowBlocks: s.workflowBlocks.filter((b) => b.id !== id),
      workflowEdges: s.workflowEdges.filter(
        (e) => e.sourceBlockId !== id && e.targetBlockId !== id,
      ),
    })),

  toggleBlockActive: (id) =>
    set((s) => ({
      workflowBlocks: s.workflowBlocks.map((b) =>
        b.id === id ? { ...b, isActive: !b.isActive } : b,
      ),
    })),

  setEndpointBlock: (id) =>
    set((s) => ({
      workflowBlocks: s.workflowBlocks.map((b) => ({
        ...b,
        isEndpoint: b.id === id,
      })),
    })),

  updateBlockPosition: (id, position) =>
    set((s) => ({
      workflowBlocks: s.workflowBlocks.map((b) =>
        b.id === id ? { ...b, position } : b,
      ),
    })),

  addEdge: (edge) => set((s) => ({ workflowEdges: [...s.workflowEdges, edge] })),

  removeEdge: (id) =>
    set((s) => ({
      workflowEdges: s.workflowEdges.filter((e) => e.id !== id),
    })),

  generateSQL: async (prompt) => {
    set({ isGeneratingSQL: true });
    try {
      const data = await apiCall<{ sql: string; explanation: string | null }>(
        "/api/automations/generate-sql",
        { method: "POST", body: JSON.stringify({ prompt }) },
      );
      if (data) {
        const { workflowBlocks } = get();
        const maxY = workflowBlocks.reduce(
          (max, b) => Math.max(max, b.position.y),
          -200,
        );
        const newBlock: WorkflowBlock = {
          id: nextBlockId(),
          sql: data.sql,
          label: prompt.slice(0, 60) + (prompt.length > 60 ? "..." : ""),
          sourceMessageId: null,
          sourceMessagePreview: prompt,
          isActive: true,
          isEndpoint: false,
          resultPreview: null,
          position: { x: 300, y: maxY + 200 },
        };
        set((s) => ({ workflowBlocks: [...s.workflowBlocks, newBlock] }));
      }
    } finally {
      set({ isGeneratingSQL: false });
    }
  },

  saveWorkflowAsAutomation: async (meta) => {
    const { workflowBlocks, workflowEdges, workflowBuilderContext } = get();
    const activeBlocks = workflowBlocks.filter((b) => b.isActive);
    if (activeBlocks.length === 0) return null;

    // Topological sort for ordered SQL chain
    const sqlQueries = topologicalSort(workflowBlocks, workflowEdges);

    // If topological sort returned nothing (no edges / disconnected),
    // fall back to active blocks in canvas Y-position order.
    const finalQueries =
      sqlQueries.length > 0
        ? sqlQueries
        : activeBlocks
            .sort((a, b) => a.position.y - b.position.y)
            .map((b) => b.sql);

    // Find the endpoint block for the nl_query
    const endpoint = workflowBlocks.find((b) => b.isEndpoint);

    const payload: CreateAutomationPayload = {
      name: meta.name,
      description: meta.description,
      nl_query: endpoint?.sourceMessagePreview || meta.name,
      sql_queries: finalQueries,
      schedule_preset: meta.schedulePreset,
      cron_expression: meta.cronExpression,
      trigger_conditions: meta.triggerConditions,
      source_conversation_id: workflowBuilderContext?.conversationId,
    };

    return await get().createAutomation(payload);
  },
}));
