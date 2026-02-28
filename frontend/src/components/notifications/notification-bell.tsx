"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNotificationStore } from "@/stores/notification-store";
import { NotificationPopover } from "./notification-popover";
import { NotificationAllModal } from "./notification-all-modal";

export function NotificationBell() {
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount);
  const fetchNotifications = useNotificationStore((s) => s.fetchNotifications);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Poll unread count every 30s
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30_000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  // Fetch full notifications when popover opens
  const handleToggle = useCallback(() => {
    setPopoverOpen((prev) => {
      if (!prev) fetchNotifications(true); // Only unread for popover
      return !prev;
    });
  }, [fetchNotifications]);

  // Close on outside click
  useEffect(() => {
    if (!popoverOpen) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [popoverOpen]);

  const handleShowAll = useCallback(() => {
    setPopoverOpen(false);
    setModalOpen(true);
  }, []);

  return (
    <>
      <div className="relative" ref={popoverRef}>
        <Button
          variant="ghost"
          size="icon"
          className="size-9 relative"
          onClick={handleToggle}
          aria-label="Notifications"
        >
          <Bell className="size-4.5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center size-4 rounded-full bg-destructive text-[10px] font-medium text-white">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Button>

        {popoverOpen && (
          <div className="absolute right-0 top-full mt-1 z-50">
            <NotificationPopover onShowAll={handleShowAll} />
          </div>
        )}
      </div>

      <NotificationAllModal open={modalOpen} onOpenChange={setModalOpen} />
    </>
  );
}
