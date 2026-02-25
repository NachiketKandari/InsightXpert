import { create } from "zustand";
import { apiCall } from "@/lib/api";
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
    const data = await apiCall<{ config: OrgConfig | null; is_admin: boolean; org_id: string | null }>("/api/client-config");
    if (!data) {
      set({ isLoading: false });
      return;
    }
    set({
      config: data.config,
      isAdmin: data.is_admin,
      orgId: data.org_id,
      isLoading: false,
    });

    if (data.config?.branding?.theme) {
      const root = document.documentElement;
      for (const [key, value] of Object.entries(data.config.branding.theme)) {
        root.style.setProperty(key, value as string);
      }
    }

    if (data.config?.branding?.display_name) {
      document.title = `${data.config.branding.display_name} - AI Data Analyst`;
    }
  },
}));
