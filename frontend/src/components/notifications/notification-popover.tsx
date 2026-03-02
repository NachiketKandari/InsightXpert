"use client";

import { Check, CheckCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useNotificationStore } from "@/stores/notification-store";
import { SEVERITY_VARIANT } from "./constants";

interface NotificationPopoverProps {
  onShowAll: () => void;
}

export function NotificationPopover({ onShowAll }: NotificationPopoverProps) {
  const notifications = useNotificationStore((s) => s.notifications);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);

  const unread = notifications.filter((n) => !n.is_read);
  const recent = unread.slice(0, 10);

  const handleMarkRead = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    markAsRead(id);
  };

  return (
    <div className="w-80 max-h-96 flex flex-col rounded-lg border border-border bg-background shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
        <span className="text-sm font-medium">Notifications</span>
        {unread.length > 0 && (
          <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={markAllAsRead}>
            <CheckCheck className="size-3 mr-1" />
            Mark all read
          </Button>
        )}
      </div>

      {/* List */}
      {recent.length === 0 ? (
        <div className="flex-1 py-6 text-center text-sm text-muted-foreground">
          No new notifications
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto min-h-0 divide-y divide-border/50">
          {recent.map((n) => (
            <div
              key={n.id}
              className="group px-3 py-2.5 hover:bg-muted/50 transition-colors bg-primary/5"
            >
              <div className="flex items-center gap-2">
                <div className="size-1.5 rounded-full bg-primary shrink-0" />
                <p className="text-sm font-medium truncate flex-1">{n.title}</p>
                <Badge variant={SEVERITY_VARIANT[n.severity] ?? "secondary"} className="text-[10px] shrink-0">
                  {n.severity}
                </Badge>
                <button
                  type="button"
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary shrink-0"
                  onClick={(e) => handleMarkRead(n.id, e)}
                  title="Mark as read"
                >
                  <Check className="size-3.5" />
                </button>
              </div>
              <p className="text-xs text-muted-foreground truncate mt-0.5 ml-3.5">
                {n.message}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-border px-3 py-1.5 text-center shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="w-full h-7 text-xs text-primary hover:text-primary hover:bg-primary/10"
          onClick={onShowAll}
        >
          See all notifications
        </Button>
      </div>
    </div>
  );
}
