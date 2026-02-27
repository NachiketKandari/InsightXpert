"use client";

import { useEffect, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useNotificationStore } from "@/stores/notification-store";
import { NotificationDetailModal } from "./notification-detail-modal";
import type { Notification } from "@/types/automation";

const SEVERITY_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  info: "secondary",
  warning: "default",
  critical: "destructive",
};

export function NotificationList() {
  const notifications = useNotificationStore((s) => s.notifications);
  const isLoading = useNotificationStore((s) => s.isLoading);
  const fetchNotifications = useNotificationStore((s) => s.fetchNotifications);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const handleClick = (notification: Notification) => {
    if (!notification.is_read) {
      markAsRead(notification.id);
    }
    setSelectedNotification(notification);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (notifications.length === 0) {
    return (
      <div className="text-center py-12">
        <Bell className="size-8 text-muted-foreground mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">No notifications yet</p>
      </div>
    );
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <>
      <div className="space-y-1">
        {unreadCount > 0 && (
          <div className="flex items-center justify-between pb-2">
            <span className="text-sm text-muted-foreground">{unreadCount} unread</span>
            <Button variant="ghost" size="sm" onClick={markAllAsRead}>
              <CheckCheck className="size-3.5 mr-1" />
              Mark all read
            </Button>
          </div>
        )}
        {notifications.map((n) => (
          <div
            key={n.id}
            className={`flex items-start gap-3 rounded-md border border-border/50 p-3 cursor-pointer transition-colors hover:bg-muted/50 ${
              !n.is_read ? "bg-primary/5 border-primary/20" : ""
            }`}
            onClick={() => handleClick(n)}
          >
            {!n.is_read && (
              <div className="size-2 rounded-full bg-primary shrink-0 mt-1.5" />
            )}
            <div className={`flex-1 min-w-0 ${n.is_read ? "ml-5" : ""}`}>
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium truncate">{n.title}</p>
                <Badge variant={SEVERITY_VARIANT[n.severity] ?? "secondary"} className="text-xs shrink-0">
                  {n.severity}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground truncate mt-0.5">
                {n.message}
              </p>
              <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                {n.automation_name && <span>{n.automation_name}</span>}
                <span>{new Date(n.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <NotificationDetailModal
        notification={selectedNotification}
        open={selectedNotification !== null}
        onOpenChange={(open) => !open && setSelectedNotification(null)}
      />
    </>
  );
}
