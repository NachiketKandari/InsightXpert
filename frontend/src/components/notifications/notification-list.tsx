"use client";

import { useEffect, useState } from "react";
import { useNotificationStore } from "@/stores/notification-store";
import { NotificationDetailModal } from "./notification-detail-modal";
import { NotificationCard } from "./notification-card";
import { NotificationFilterBar, NotificationLoading, NotificationEmptyState } from "./notification-shared";
import type { Notification } from "@/types/automation";

type Filter = "all" | "unread";

export function NotificationList() {
  const notifications = useNotificationStore((s) => s.notifications);
  const isLoading = useNotificationStore((s) => s.isLoading);
  const fetchNotifications = useNotificationStore((s) => s.fetchNotifications);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const handleClick = (notification: Notification) => {
    if (!notification.is_read) {
      markAsRead(notification.id);
    }
    setSelectedNotification(notification);
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const filtered = filter === "unread" ? notifications.filter((n) => !n.is_read) : notifications;

  if (isLoading) {
    return <NotificationLoading />;
  }

  if (notifications.length === 0) {
    return <NotificationEmptyState filter="all" />;
  }

  return (
    <>
      <div className="space-y-1">
        <NotificationFilterBar
          total={notifications.length}
          unreadCount={unreadCount}
          filter={filter}
          onFilterChange={setFilter}
          onMarkAllRead={markAllAsRead}
          className="pb-2"
        />

        {filtered.length === 0 ? (
          <NotificationEmptyState filter={filter} />
        ) : (
          filtered.map((n) => (
            <NotificationCard key={n.id} notification={n} onClick={handleClick} onMarkRead={markAsRead} />
          ))
        )}
      </div>

      <NotificationDetailModal
        notification={selectedNotification}
        open={selectedNotification !== null}
        onOpenChange={(open) => !open && setSelectedNotification(null)}
      />
    </>
  );
}
