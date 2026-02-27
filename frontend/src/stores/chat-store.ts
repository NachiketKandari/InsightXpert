import { create } from "zustand";
import { persist } from "zustand/middleware";
import { apiFetch } from "@/lib/api";
import type {
  ChatChunk,
  Conversation,
  Message,
  AgentStep,
} from "@/types/chat";

function generateId() {
  return Math.random().toString(36).slice(2, 10);
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  isStreaming: boolean;
  streamingConversationId: string | null;
  agentSteps: AgentStep[];
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;
  sqlExecutorOpen: boolean;
  datasetViewerOpen: boolean;
  sampleQuestionsOpen: boolean;
  pendingInput: string | null;
  pendingClarification: string | null;
  skipClarificationNext: boolean;

  isLoadingConversation: boolean;

  // Derived
  activeConversation: () => Conversation | null;

  // Actions
  initFromStorage: () => Promise<void>;
  newConversation: () => string;
  clearActiveConversation: () => void;
  setActiveConversation: (id: string) => void;
  loadConversationMessages: (id: string) => Promise<void>;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;

  addUserMessage: (content: string) => void;
  startAssistantMessage: () => void;
  appendChunk: (chunk: ChatChunk) => void;
  finishStreaming: (conversationId?: string) => void;

  addAgentStep: (step: AgentStep) => void;
  updateAgentStep: (id: string, updates: Partial<AgentStep>) => void;
  clearAgentSteps: () => void;
  updateLastAssistantTime: (wallTimeMs: number, convId?: string) => void;

  toggleLeftSidebar: () => void;
  toggleRightSidebar: () => void;
  setLeftSidebar: (open: boolean) => void;
  setRightSidebar: (open: boolean) => void;
  setSqlExecutorOpen: (open: boolean) => void;
  setDatasetViewerOpen: (open: boolean) => void;
  setSampleQuestionsOpen: (open: boolean) => void;
  setPendingInput: (text: string | null) => void;
  setPendingClarification: (text: string | null) => void;
  setSkipClarificationNext: (skip: boolean) => void;
}

export const useChatStore = create<ChatState>()(persist((set, get) => ({
  conversations: [],
  activeConversationId: null,
  isStreaming: false,
  streamingConversationId: null,
  agentSteps: [],
  leftSidebarOpen: false,
  rightSidebarOpen: false,
  sqlExecutorOpen: false,
  datasetViewerOpen: false,
  sampleQuestionsOpen: false,
  pendingInput: null,
  pendingClarification: null,
  skipClarificationNext: false,
  isLoadingConversation: false,

  activeConversation: () => {
    const { conversations, activeConversationId } = get();
    return conversations.find((c) => c.id === activeConversationId) || null;
  },

  initFromStorage: async () => {
    try {
      const res = await apiFetch("/api/conversations");
      if (!res.ok) {
        console.error("[chat-store] Failed to load conversations:", res.status, res.statusText);
        return;
      }
      const data = await res.json();
      const conversations: Conversation[] = data.map(
        (c: { id: string; title: string; messages?: Message[]; created_at: string; updated_at: string }) => ({
          id: c.id,
          title: c.title,
          messages: c.messages || [],
          createdAt: new Date(c.created_at).getTime(),
          updatedAt: new Date(c.updated_at).getTime(),
        })
      );
      set((state) => {
        // Merge: preserve locally-created conversations that aren't on the server yet
        const serverIds = new Set(conversations.map((c: Conversation) => c.id));
        const localOnly = state.conversations.filter((c) => !serverIds.has(c.id));
        const merged = [...localOnly, ...conversations];

        // If activeConversationId points to a conversation that no longer exists, clear it
        const activeStillExists = merged.some((c) => c.id === state.activeConversationId);
        return {
          conversations: merged,
          ...(state.activeConversationId && !activeStillExists
            ? { activeConversationId: null }
            : {}),
        };
      });
    } catch (err) {
      console.error("[chat-store] Error loading conversations:", err);
    }
  },

  newConversation: () => {
    const id = generateId();
    const now = Date.now();
    const conv: Conversation = {
      id,
      title: "New Chat",
      messages: [],
      createdAt: now,
      updatedAt: now,
    };
    set((state) => {
      const conversations = [conv, ...state.conversations];
      return { conversations, activeConversationId: id, agentSteps: [] };
    });
    return id;
  },

  clearActiveConversation: () => {
    set({ activeConversationId: null, agentSteps: [] });
  },

  setActiveConversation: (id) => {
    set({ activeConversationId: id, agentSteps: [] });
    // Lazy-load messages from the server if the conversation was loaded
    // from initFromStorage (server-side) and has no messages yet.
    // Skip for locally-created conversations (createdAt within last 5s)
    // since they haven't been persisted to the backend yet.
    const conv = get().conversations.find((c) => c.id === id);
    if (conv && conv.messages.length === 0) {
      const isRecentlyCreated = Date.now() - conv.createdAt < 5000;
      if (!isRecentlyCreated) {
        set({ isLoadingConversation: true });
        get().loadConversationMessages(id);
      }
    }
  },

  loadConversationMessages: async (id) => {
    try {
      const res = await apiFetch(`/api/conversations/${id}`);
      if (!res.ok) {
        console.error("[chat-store] Failed to load messages for", id, ":", res.status, res.statusText);
        set({ isLoadingConversation: false });
        return;
      }
      const data = await res.json();
      const messages: Message[] = (data.messages || []).map(
        (m: { id: string; role: "user" | "assistant"; content: string; chunks?: ChatChunk[]; feedback?: boolean | null; feedback_comment?: string | null; input_tokens?: number | null; output_tokens?: number | null; generation_time_ms?: number | null; created_at: string }) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          chunks: m.chunks || [],
          feedback: m.feedback ?? null,
          feedbackComment: m.feedback_comment ?? null,
          inputTokens: m.input_tokens ?? null,
          outputTokens: m.output_tokens ?? null,
          generationTimeMs: m.generation_time_ms ?? null,
          timestamp: new Date(m.created_at).getTime(),
        })
      );
      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === id ? { ...c, messages } : c
        ),
        isLoadingConversation: false,
      }));
    } catch (err) {
      console.error("[chat-store] Error loading messages for", id, ":", err);
      set({ isLoadingConversation: false });
    }
  },

  deleteConversation: (id) => {
    set((state) => {
      const conversations = state.conversations.filter((c) => c.id !== id);
      const activeId =
        state.activeConversationId === id
          ? conversations[0]?.id || null
          : state.activeConversationId;
      return { conversations, activeConversationId: activeId };
    });
    // Fire-and-forget API call
    apiFetch(`/api/conversations/${id}`, { method: "DELETE" }).catch(() => {});
  },

  renameConversation: (id, title) => {
    set((state) => {
      const conversations = state.conversations.map((c) =>
        c.id === id ? { ...c, title, updatedAt: Date.now() } : c
      );
      return { conversations };
    });
    // Fire-and-forget API call
    apiFetch(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }).catch(() => {});
  },

  addUserMessage: (content) => {
    const msg: Message = {
      id: generateId(),
      role: "user",
      content,
      chunks: [],
      timestamp: Date.now(),
    };

    set((state) => {
      const convId = state.activeConversationId;
      if (!convId) return state;

      const conversations = state.conversations.map((c) => {
        if (c.id !== convId) return c;
        const title =
          c.messages.length === 0
            ? content.slice(0, 50) + (content.length > 50 ? "..." : "")
            : c.title;
        return {
          ...c,
          title,
          messages: [...c.messages, msg],
          updatedAt: Date.now(),
        };
      });

      return { conversations };
    });
  },

  startAssistantMessage: () => {
    const msg: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      chunks: [],
      timestamp: Date.now(),
    };

    set((state) => {
      const convId = state.activeConversationId;
      if (!convId) return state;

      const conversations = state.conversations.map((c) => {
        if (c.id !== convId) return c;
        return {
          ...c,
          messages: [...c.messages, msg],
          updatedAt: Date.now(),
        };
      });

      return { conversations, isStreaming: true, streamingConversationId: convId };
    });
  },

  appendChunk: (chunk) => {
    set((state) => {
      // Target the conversation the chunk belongs to (from the backend),
      // falling back to the active conversation. This prevents chunks from
      // an old stream leaking into a newly-created conversation.
      const convId = chunk.conversation_id || state.activeConversationId;
      if (!convId) return state;

      const conversations = state.conversations.map((c) => {
        if (c.id !== convId) return c;

        const messages = [...c.messages];
        const lastMsg = messages[messages.length - 1];
        if (!lastMsg || lastMsg.role !== "assistant") return c;

        // Metrics chunk: update observability fields, don't add to chunks array
        if (chunk.type === "metrics" && chunk.data) {
          const d = chunk.data as { input_tokens?: number; output_tokens?: number; generation_time_ms?: number };
          const updated: Message = {
            ...lastMsg,
            inputTokens: d.input_tokens ?? lastMsg.inputTokens,
            outputTokens: d.output_tokens ?? lastMsg.outputTokens,
            generationTimeMs: d.generation_time_ms ?? lastMsg.generationTimeMs,
          };
          messages[messages.length - 1] = updated;
          return { ...c, messages };
        }

        const updated: Message = {
          ...lastMsg,
          chunks: [...lastMsg.chunks, chunk],
          content:
            chunk.type === "answer" && chunk.content
              ? chunk.content
              : lastMsg.content,
        };
        messages[messages.length - 1] = updated;

        return { ...c, messages, updatedAt: Date.now() };
      });

      return { conversations };
    });
  },

  finishStreaming: (conversationId?: string) => {
    set((state) => {
      // If a conversationId is provided (from the stream's closure), only
      // clear streaming if it matches the currently-streaming conversation.
      // This prevents an old stream's onDone from killing a newer stream.
      if (conversationId && state.streamingConversationId && conversationId !== state.streamingConversationId) {
        return state;
      }
      return { isStreaming: false, streamingConversationId: null };
    });
  },

  addAgentStep: (step) => {
    set((state) => ({ agentSteps: [...state.agentSteps, step] }));
  },

  updateAgentStep: (id, updates) => {
    set((state) => ({
      agentSteps: state.agentSteps.map((s) =>
        s.id === id ? { ...s, ...updates } : s
      ),
    }));
  },

  clearAgentSteps: () => {
    set({ agentSteps: [] });
  },

  updateLastAssistantTime: (wallTimeMs, convId) => {
    set((state) => {
      const targetId = convId || state.streamingConversationId || state.activeConversationId;
      if (!targetId) return state;

      const conversations = state.conversations.map((c) => {
        if (c.id !== targetId) return c;
        const messages = [...c.messages];
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === "assistant") {
            messages[i] = { ...messages[i], wallTimeMs };
            break;
          }
        }
        return { ...c, messages };
      });

      return { conversations };
    });
  },

  toggleLeftSidebar: () => {
    set((state) => ({ leftSidebarOpen: !state.leftSidebarOpen }));
  },

  toggleRightSidebar: () => {
    set((state) => ({ rightSidebarOpen: !state.rightSidebarOpen }));
  },

  setLeftSidebar: (open) => {
    set({ leftSidebarOpen: open });
  },

  setRightSidebar: (open) => {
    set({ rightSidebarOpen: open });
  },

  setSqlExecutorOpen: (open) => {
    set({ sqlExecutorOpen: open });
  },

  setDatasetViewerOpen: (open) => {
    set({ datasetViewerOpen: open });
  },

  setSampleQuestionsOpen: (open) => {
    set({ sampleQuestionsOpen: open });
  },

  setPendingInput: (text) => {
    set({ pendingInput: text });
  },

  setPendingClarification: (text) => {
    set({ pendingClarification: text });
  },

  setSkipClarificationNext: (skip) => {
    set({ skipClarificationNext: skip });
  },
}), {
  name: "insightxpert-chat",
  storage: {
    getItem: (name) => {
      try {
        const raw = sessionStorage.getItem(name);
        return raw ? JSON.parse(raw) : null;
      } catch {
        return null;
      }
    },
    setItem: (name, value) => {
      try { sessionStorage.setItem(name, JSON.stringify(value)); } catch { /* storage full or unavailable */ }
    },
    removeItem: (name) => {
      try { sessionStorage.removeItem(name); } catch { /* unavailable */ }
    },
  },
  partialize: (state) => ({
    conversations: state.conversations.map((c) => ({
      ...c,
      messages: [] as Message[],
    })),
  }) as unknown as ChatState,
}));
