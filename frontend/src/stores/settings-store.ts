import { create } from "zustand";
import { apiFetch, apiCall } from "@/lib/api";
import type { AgentMode } from "@/lib/sse-client";

interface ProviderModels {
  provider: string;
  models: string[];
}

interface SettingsState {
  currentProvider: string;
  currentModel: string;
  providers: ProviderModels[];
  loading: boolean;
  agentMode: AgentMode;

  fetchConfig: () => Promise<void>;
  switchModel: (provider: string, model: string) => Promise<void>;
  setAgentMode: (mode: AgentMode) => void;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  currentProvider: "gemini",
  currentModel: "gemini-2.5-flash",
  providers: [],
  loading: false,
  agentMode: "agentic" as AgentMode,

  fetchConfig: async () => {
    set({ loading: true });
    const data = await apiCall<{ current_provider: string; current_model: string; providers: ProviderModels[] }>("/api/config");
    if (data) {
      set({
        currentProvider: data.current_provider,
        currentModel: data.current_model,
        providers: data.providers,
      });
    }
    set({ loading: false });
  },

  switchModel: async (provider: string, model: string) => {
    const prev = { provider: get().currentProvider, model: get().currentModel };
    // Optimistic update
    set({ currentProvider: provider, currentModel: model });

    try {
      const res = await apiFetch("/api/config/switch", {
        method: "POST",
        body: JSON.stringify({ provider, model }),
      });
      if (!res.ok) {
        // Revert on failure
        set({ currentProvider: prev.provider, currentModel: prev.model });
      }
    } catch {
      set({ currentProvider: prev.provider, currentModel: prev.model });
    }
  },

  setAgentMode: (mode) => set({ agentMode: mode }),
}));
