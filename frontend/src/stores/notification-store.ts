import { create } from "zustand";
import { apiCall, apiFetch } from "@/lib/api";
import type { Notification } from "@/types/automation";

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  isLoading: boolean;

  fetchNotifications: (unreadOnly?: boolean) => Promise<void>;
  fetchUnreadCount: () => Promise<void>;
  markAsRead: (id: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,
  isLoading: false,

  fetchNotifications: async (unreadOnly = false) => {
    set({ isLoading: true });
    const params = unreadOnly ? "?unread_only=true" : "";
    const data = await apiCall<Notification[]>(`/api/notifications${params}`);
    set({ notifications: data ?? [], isLoading: false });
  },

  fetchUnreadCount: async () => {
    const data = await apiCall<{ count: number }>("/api/notifications/count");
    if (data) set({ unreadCount: data.count });
  },

  markAsRead: async (id) => {
    await apiFetch(`/api/notifications/${id}/read`, { method: "PATCH" });
    set((s) => ({
      notifications: s.notifications.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }));
  },

  markAllAsRead: async () => {
    await apiFetch("/api/notifications/mark-all-read", { method: "POST" });
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, is_read: true })),
      unreadCount: 0,
    }));
  },
}));
