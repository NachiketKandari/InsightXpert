import { create } from "zustand";
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
  agentSteps: AgentStep[];
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;

  // Derived
  activeConversation: () => Conversation | null;

  // Actions
  initFromStorage: () => Promise<void>;
  newConversation: () => string;
  setActiveConversation: (id: string) => void;
  loadConversationMessages: (id: string) => Promise<void>;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;

  addUserMessage: (content: string) => void;
  startAssistantMessage: () => void;
  appendChunk: (chunk: ChatChunk) => void;
  finishStreaming: () => void;

  addAgentStep: (step: AgentStep) => void;
  updateAgentStep: (id: string, updates: Partial<AgentStep>) => void;
  clearAgentSteps: () => void;

  toggleLeftSidebar: () => void;
  toggleRightSidebar: () => void;
  setLeftSidebar: (open: boolean) => void;
  setRightSidebar: (open: boolean) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  isStreaming: false,
  agentSteps: [],
  leftSidebarOpen: true,
  rightSidebarOpen: true,

  activeConversation: () => {
    const { conversations, activeConversationId } = get();
    return conversations.find((c) => c.id === activeConversationId) || null;
  },

  initFromStorage: async () => {
    try {
      const res = await apiFetch("/api/conversations");
      if (!res.ok) return;
      const data = await res.json();
      const conversations: Conversation[] = data.map(
        (c: { id: string; title: string; messages?: Message[]; created_at: number; updated_at: number }) => ({
          id: c.id,
          title: c.title,
          messages: c.messages || [],
          createdAt: c.created_at,
          updatedAt: c.updated_at,
        })
      );
      set({ conversations });
    } catch {
      // silently fail
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

  setActiveConversation: (id) => {
    set({ activeConversationId: id, agentSteps: [] });
    // Lazy-load messages if the conversation has none
    const conv = get().conversations.find((c) => c.id === id);
    if (conv && conv.messages.length === 0) {
      get().loadConversationMessages(id);
    }
  },

  loadConversationMessages: async (id) => {
    try {
      const res = await apiFetch(`/api/conversations/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      const messages: Message[] = (data.messages || []).map(
        (m: { id: string; role: "user" | "assistant"; content: string; chunks?: ChatChunk[]; created_at: string }) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          chunks: m.chunks || [],
          timestamp: new Date(m.created_at).getTime(),
        })
      );
      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === id ? { ...c, messages } : c
        ),
      }));
    } catch {
      // silently fail
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

      return { conversations, isStreaming: true };
    });
  },

  appendChunk: (chunk) => {
    set((state) => {
      const convId = state.activeConversationId;
      if (!convId) return state;

      const conversations = state.conversations.map((c) => {
        if (c.id !== convId) return c;

        const messages = [...c.messages];
        const lastMsg = messages[messages.length - 1];
        if (!lastMsg || lastMsg.role !== "assistant") return c;

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

  finishStreaming: () => {
    set({ isStreaming: false });
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
}));
