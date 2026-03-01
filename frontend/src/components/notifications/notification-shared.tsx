import { Bell, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ListLoading, ListEmptyState } from "@/components/ui/list-states";

/* ---------- Filter bar ---------- */

interface NotificationFilterBarProps {
  total: number;
  unreadCount: number;
  filter: "all" | "unread";
  onFilterChange: (filter: "all" | "unread") => void;
  onMarkAllRead: () => void;
  markAllLabel?: string;
  className?: string;
}

export function NotificationFilterBar({
  total,
  unreadCount,
  filter,
  onFilterChange,
  onMarkAllRead,
  markAllLabel = "Mark all read",
  className,
}: NotificationFilterBarProps) {
  return (
    <div className={`flex items-center justify-between ${className ?? ""}`}>
      <div className="flex items-center gap-1">
        <Button
          variant={filter === "all" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={() => onFilterChange("all")}
        >
          All ({total})
        </Button>
        <Button
          variant={filter === "unread" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={() => onFilterChange("unread")}
        >
          Unread ({unreadCount})
        </Button>
      </div>
      {unreadCount > 0 && (
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onMarkAllRead}>
          <CheckCheck className="size-3.5 mr-1" />
          {markAllLabel}
        </Button>
      )}
    </div>
  );
}

/* ---------- Loading spinner ---------- */

export function NotificationLoading() {
  return <ListLoading />;
}

/* ---------- Empty state ---------- */

interface NotificationEmptyStateProps {
  filter: "all" | "unread";
}

export function NotificationEmptyState({ filter }: NotificationEmptyStateProps) {
  return (
    <ListEmptyState
      icon={<Bell className="size-8 text-muted-foreground mx-auto mb-2" />}
      message={filter === "unread" ? "No unread notifications" : "No notifications yet"}
    />
  );
}
