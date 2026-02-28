import { Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Notification } from "@/types/automation";
import { SEVERITY_VARIANT } from "./constants";

interface NotificationCardProps {
  notification: Notification;
  onClick: (n: Notification) => void;
  onMarkRead?: (id: string) => void;
  showUserEmail?: boolean;
  isSuperAdmin?: boolean;
  isSelected?: boolean;
}

export function NotificationCard({
  notification: n,
  onClick,
  onMarkRead,
  showUserEmail,
  isSuperAdmin,
  isSelected,
}: NotificationCardProps) {
  return (
    <div
      className={`group flex items-start gap-3 rounded-md border p-3 cursor-pointer transition-colors hover:bg-muted/50 ${
        isSelected
          ? "border-primary/40 bg-primary/10"
          : !n.is_read
            ? "border-primary/20 bg-primary/5"
            : "border-border/50"
      }`}
      onClick={() => onClick(n)}
    >
      {!n.is_read && (
        <div className="size-2 rounded-full bg-primary shrink-0 mt-1.5" />
      )}
      <div className={`flex-1 min-w-0 ${n.is_read ? "ml-5" : ""}`}>
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium truncate">{n.title}</p>
          <Badge
            variant={SEVERITY_VARIANT[n.severity] ?? "secondary"}
            className="text-xs shrink-0"
          >
            {n.severity}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          {n.message}
        </p>
        <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
          {showUserEmail && n.user_email && (
            <span className="font-medium text-foreground/70">
              {n.user_email}
            </span>
          )}
          {isSuperAdmin && n.user_org_id && (
            <Badge variant="outline" className="text-[10px] h-4">
              {n.user_org_id}
            </Badge>
          )}
          {isSuperAdmin && n.user_is_admin !== undefined && (
            <Badge
              variant={n.user_is_admin ? "default" : "secondary"}
              className="text-[10px] h-4"
            >
              {n.user_is_admin ? "admin" : "user"}
            </Badge>
          )}
          {n.automation_name && <span>{n.automation_name}</span>}
          <span>{new Date(n.created_at).toLocaleString()}</span>
        </div>
      </div>
      {!n.is_read && onMarkRead && (
        <button
          type="button"
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary shrink-0 mt-0.5"
          onClick={(e) => {
            e.stopPropagation();
            onMarkRead(n.id);
          }}
          title="Mark as read"
        >
          <Check className="size-4" />
        </button>
      )}
    </div>
  );
}
