import { create } from "zustand";
import { API_BASE_URL } from "@/lib/constants";

interface ProviderModels {
  provider: string;
  models: string[];
}

interface SettingsState {
  currentProvider: string;
  currentModel: string;
  providers: ProviderModels[];
  loading: boolean;

  fetchConfig: () => Promise<void>;
  switchModel: (provider: string, model: string) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  currentProvider: "gemini",
  currentModel: "gemini-2.5-flash",
  providers: [],
  loading: false,

  fetchConfig: async () => {
    try {
      set({ loading: true });
      const res = await fetch(`${API_BASE_URL}/api/config`, {
        credentials: "include",
      });
      if (!res.ok) return;
      const data = await res.json();
      set({
        currentProvider: data.current_provider,
        currentModel: data.current_model,
        providers: data.providers,
      });
    } catch {
      // Silently fail — keep defaults
    } finally {
      set({ loading: false });
    }
  },

  switchModel: async (provider: string, model: string) => {
    const prev = { provider: get().currentProvider, model: get().currentModel };
    // Optimistic update
    set({ currentProvider: provider, currentModel: model });

    try {
      const res = await fetch(`${API_BASE_URL}/api/config/switch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
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
}));
