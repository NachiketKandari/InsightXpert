"use client";

import Link from "next/link";
import { CheckCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useNotificationStore } from "@/stores/notification-store";

const SEVERITY_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  info: "secondary",
  warning: "default",
  critical: "destructive",
};

interface NotificationPopoverProps {
  onClose: () => void;
}

export function NotificationPopover({ onClose }: NotificationPopoverProps) {
  const notifications = useNotificationStore((s) => s.notifications);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);

  const recent = notifications.slice(0, 10);

  const handleMarkRead = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    markAsRead(id);
  };

  return (
    <div className="w-80 max-h-96 overflow-y-auto rounded-lg border border-border bg-background shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-medium">Notifications</span>
        {notifications.some((n) => !n.is_read) && (
          <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={markAllAsRead}>
            <CheckCheck className="size-3 mr-1" />
            Mark all read
          </Button>
        )}
      </div>

      {/* List */}
      {recent.length === 0 ? (
        <div className="py-6 text-center text-sm text-muted-foreground">
          No notifications
        </div>
      ) : (
        <div className="divide-y divide-border/50">
          {recent.map((n) => (
            <div
              key={n.id}
              className={`px-3 py-2.5 cursor-pointer hover:bg-muted/50 transition-colors ${
                !n.is_read ? "bg-primary/5" : ""
              }`}
              onClick={(e) => {
                if (!n.is_read) handleMarkRead(n.id, e);
              }}
            >
              <div className="flex items-center gap-2">
                {!n.is_read && <div className="size-1.5 rounded-full bg-primary shrink-0" />}
                <p className="text-sm font-medium truncate flex-1">{n.title}</p>
                <Badge variant={SEVERITY_VARIANT[n.severity] ?? "secondary"} className="text-[10px] shrink-0">
                  {n.severity}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground truncate mt-0.5 ml-3.5">
                {n.message}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-border px-3 py-2 text-center">
        <Link
          href="/admin/notifications"
          className="text-xs text-primary hover:underline"
          onClick={onClose}
        >
          See all notifications
        </Link>
      </div>
    </div>
  );
}
