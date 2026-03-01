"use client";

import { useCallback } from "react";
import { Bell } from "lucide-react";
import { useNotificationStore } from "@/stores/notification-store";
import { HeaderBell } from "@/components/ui/header-bell";
import { NotificationPopover } from "./notification-popover";
import { NotificationAllModal } from "./notification-all-modal";

export function NotificationBell() {
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount);
  const fetchNotifications = useNotificationStore((s) => s.fetchNotifications);

  const handleOpen = useCallback(() => fetchNotifications(true), [fetchNotifications]);

  return (
    <HeaderBell
      icon={<Bell className="size-4.5" />}
      count={unreadCount}
      badgeClassName="bg-destructive"
      label="Notifications"
      pollIntervalMs={30_000}
      onPoll={fetchUnreadCount}
      onOpen={handleOpen}
      renderPopover={({ showAll }) => (
        <NotificationPopover onShowAll={showAll} />
      )}
      renderModal={(open, onOpenChange) => (
        <NotificationAllModal open={open} onOpenChange={onOpenChange} />
      )}
    />
  );
}
