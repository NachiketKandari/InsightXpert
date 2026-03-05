import { create } from "zustand";
import { apiCall, apiFetch } from "@/lib/api";
import type {
  UserDatabaseConnection,
  CreateConnectionPayload,
  TestConnectionResult,
} from "@/types/connection";

interface ConnectionState {
  connections: UserDatabaseConnection[];
  isLoading: boolean;
  error: string | null;

  fetchConnections: () => Promise<void>;
  createConnection: (payload: CreateConnectionPayload) => Promise<UserDatabaseConnection | null>;
  deleteConnection: (id: string) => Promise<boolean>;
  setActive: (id: string, active: boolean) => Promise<void>;
  testConnection: (id: string) => Promise<TestConnectionResult | null>;
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  connections: [],
  isLoading: false,
  error: null,

  fetchConnections: async () => {
    set({ isLoading: true, error: null });
    const data = await apiCall<UserDatabaseConnection[]>("/api/connections");
    set({ connections: data ?? [], isLoading: false });
  },

  createConnection: async (payload) => {
    const data = await apiCall<UserDatabaseConnection>("/api/connections", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (data) {
      set((s) => ({ connections: [data, ...s.connections] }));
    }
    return data;
  },

  deleteConnection: async (id) => {
    const res = await apiFetch(`/api/connections/${id}`, { method: "DELETE" });
    if (res.ok) {
      set((s) => ({
        connections: s.connections.filter((c) => c.id !== id),
      }));
      return true;
    }
    return false;
  },

  setActive: async (id, active) => {
    const data = await apiCall<UserDatabaseConnection>(
      `/api/connections/${id}/active`,
      {
        method: "PATCH",
        body: JSON.stringify({ active }),
      }
    );
    if (data) {
      set((s) => ({
        connections: s.connections.map((c) => {
          if (c.id === id) return data;
          // When activating one, deactivate siblings
          if (active && c.is_active) return { ...c, is_active: false };
          return c;
        }),
      }));
    }
  },

  testConnection: async (id) => {
    return await apiCall<TestConnectionResult>(`/api/connections/${id}/test`, {
      method: "POST",
    });
  },
}));
