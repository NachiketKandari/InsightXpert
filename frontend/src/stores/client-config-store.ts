import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import type { OrgConfig } from "@/types/admin";

interface ClientConfigState {
  config: OrgConfig | null;
  isAdmin: boolean;
  orgId: string | null;
  isLoading: boolean;
  fetchConfig: () => Promise<void>;
}

export const useClientConfigStore = create<ClientConfigState>((set) => ({
  config: null,
  isAdmin: false,
  orgId: null,
  isLoading: true,

  fetchConfig: async () => {
    set({ isLoading: true });
    try {
      const res = await apiFetch("/api/client-config");
      if (!res.ok) {
        set({ isLoading: false });
        return;
      }
      const data = await res.json();
      set({
        config: data.config,
        isAdmin: data.is_admin,
        orgId: data.org_id,
        isLoading: false,
      });

      // Apply branding theme CSS variables
      if (data.config?.branding?.theme) {
        const root = document.documentElement;
        for (const [key, value] of Object.entries(data.config.branding.theme)) {
          root.style.setProperty(key, value as string);
        }
      }

      // Update document title with display name
      if (data.config?.branding?.display_name) {
        document.title = `${data.config.branding.display_name} - AI Data Analyst`;
      }
    } catch {
      set({ isLoading: false });
    }
  },
}));
