import { create } from "zustand";
import { apiCall } from "@/lib/api";
import type { Notification } from "@/types/automation";

interface NotificationState {
  notifications: Notification[];
  allNotifications: Notification[];
  unreadCount: number;
  isLoading: boolean;
  isLoadingAll: boolean;

  fetchNotifications: (unreadOnly?: boolean) => Promise<void>;
  fetchAllNotifications: (unreadOnly?: boolean) => Promise<void>;
  fetchUnreadCount: () => Promise<void>;
  markAsRead: (id: string) => Promise<void>;
  markAllAsRead: () => Promise<void>;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],
  allNotifications: [],
  unreadCount: 0,
  isLoading: false,
  isLoadingAll: false,

  fetchNotifications: async (unreadOnly = false) => {
    set({ isLoading: true });
    try {
      const params = unreadOnly ? "?unread_only=true" : "";
      const data = await apiCall<Notification[]>(`/api/notifications${params}`);
      set({ notifications: data ?? [] });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchAllNotifications: async (unreadOnly = false) => {
    set({ isLoadingAll: true });
    try {
      const params = unreadOnly ? "?unread_only=true" : "";
      const data = await apiCall<Notification[]>(`/api/notifications/all${params}`);
      set({ allNotifications: data ?? [] });
    } finally {
      set({ isLoadingAll: false });
    }
  },

  fetchUnreadCount: async () => {
    const data = await apiCall<{ count: number }>("/api/notifications/count");
    if (data) set({ unreadCount: data.count });
  },

  markAsRead: async (id) => {
    // Optimistic update — dismiss immediately
    const prev = get();
    set((s) => ({
      notifications: s.notifications.map((n) =>
        n.id === id ? { ...n, is_read: true } : n,
      ),
      allNotifications: s.allNotifications.map((n) =>
        n.id === id ? { ...n, is_read: true } : n,
      ),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }));
    // Fire-and-forget API call; revert on failure
    apiCall<{ status: string }>(
      `/api/notifications/${id}/read`,
      { method: "PATCH" },
    ).catch(() => {
      set({
        notifications: prev.notifications,
        allNotifications: prev.allNotifications,
        unreadCount: prev.unreadCount,
      });
    });
  },

  markAllAsRead: async () => {
    // Optimistic update — dismiss all immediately
    const prev = get();
    set((s) => {
      const ownIds = new Set(s.notifications.map((n) => n.id));
      return {
        notifications: s.notifications.map((n) => ({ ...n, is_read: true })),
        allNotifications: s.allNotifications.map((n) =>
          ownIds.has(n.id) ? { ...n, is_read: true } : n,
        ),
        unreadCount: 0,
      };
    });
    // Fire-and-forget API call; revert on failure
    apiCall<{ status: string; count: number }>(
      "/api/notifications/mark-all-read",
      { method: "POST" },
    ).catch(() => {
      set({
        notifications: prev.notifications,
        allNotifications: prev.allNotifications,
        unreadCount: prev.unreadCount,
      });
    });
  },
}));
