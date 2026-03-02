import { create } from "zustand";
import { apiFetch } from "@/lib/api";

interface AuthUser {
  id: string;
  email: string;
  is_admin: boolean;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  clearError: () => void;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isLoading: true,
  error: null,

  clearError: () => set({ error: null }),

  login: async (email: string, password: string) => {
    set({ error: null, isLoading: true });
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        set({
          error: data?.detail || "Invalid email or password",
          isLoading: false,
        });
        return;
      }
      const data = await res.json();
      set({ user: { id: data.id, email: data.email, is_admin: data.is_admin ?? false }, token: data.token ?? null, isLoading: false });
    } catch {
      set({ error: "Network error. Please try again.", isLoading: false });
    }
  },

  register: async (email: string, password: string) => {
    set({ error: null, isLoading: true });
    try {
      const res = await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        set({
          error: data?.detail || "Registration failed",
          isLoading: false,
        });
        return;
      }
      const data = await res.json();
      set({ user: { id: data.id, email: data.email, is_admin: data.is_admin ?? false }, token: data.token ?? null, isLoading: false });
    } catch {
      set({ error: "Network error. Please try again.", isLoading: false });
    }
  },

  logout: async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch {
      // proceed with local logout even if request fails
    }
    set({ user: null, token: null });
  },

  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const res = await apiFetch("/api/auth/me");
      if (!res.ok) {
        set({ user: null, token: null, isLoading: false });
        return;
      }
      const data = await res.json();
      set({ user: { id: data.id, email: data.email, is_admin: data.is_admin ?? false }, token: data.token ?? null, isLoading: false });
    } catch {
      set({ user: null, token: null, isLoading: false });
    }
  },
}));
