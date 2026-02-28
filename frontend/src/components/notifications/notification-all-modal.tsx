"use client";

import { useEffect, useState } from "react";
import { Bell, ExternalLink, Clock, Zap } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useNotificationStore } from "@/stores/notification-store";
import { useClientConfig } from "@/hooks/use-client-config";
import { NotificationCard } from "./notification-card";
import { NotificationFilterBar, NotificationLoading, NotificationEmptyState } from "./notification-shared";
import { SEVERITY_VARIANT } from "./constants";
import type { Notification } from "@/types/automation";

type Filter = "all" | "unread";

interface NotificationAllModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NotificationAllModal({ open, onOpenChange }: NotificationAllModalProps) {
  const { isAdmin, orgId } = useClientConfig();
  const allNotifications = useNotificationStore((s) => s.allNotifications);
  const isLoadingAll = useNotificationStore((s) => s.isLoadingAll);
  const fetchAllNotifications = useNotificationStore((s) => s.fetchAllNotifications);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);

  useEffect(() => {
    if (open) fetchAllNotifications();
  }, [open, fetchAllNotifications]);

  // Clear selection when modal closes
  useEffect(() => {
    if (!open) setSelectedNotification(null);
  }, [open]);

  const unreadCount = allNotifications.filter((n) => !n.is_read).length;
  const filtered = filter === "unread"
    ? allNotifications.filter((n) => !n.is_read)
    : allNotifications;

  const handleClick = (notification: Notification) => {
    if (!notification.is_read) {
      markAsRead(notification.id);
    }
    setSelectedNotification(notification);
  };

  const handleNavigateToAutomation = (automationId: string) => {
    onOpenChange(false);
    window.location.href = `/admin/automations?highlight=${automationId}`;
  };

  // Determine the view label based on role
  const isOrgAdmin = isAdmin && !!orgId;
  const isSuperAdmin = isAdmin && !orgId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-4xl h-[80vh] flex flex-col p-0 bg-card border-border/60 shadow-2xl">
        <DialogHeader className="px-6 pt-5 pb-3 shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Bell className="size-5" />
            {isSuperAdmin
              ? "All Notifications"
              : isOrgAdmin
                ? "Organization Notifications"
                : "Your Notifications"}
          </DialogTitle>
          <DialogDescription>
            {isSuperAdmin
              ? "Notifications across all users and organizations"
              : isOrgAdmin
                ? "Notifications for all users in your organization"
                : "Your notification history"}
          </DialogDescription>
        </DialogHeader>

        {/* Filter bar */}
        <NotificationFilterBar
          total={allNotifications.length}
          unreadCount={unreadCount}
          filter={filter}
          onFilterChange={setFilter}
          onMarkAllRead={markAllAsRead}
          markAllLabel={isAdmin ? "Mark my notifications read" : "Mark all read"}
          className="border-b border-border px-6 pb-3 shrink-0"
        />

        {/* Split view: list + detail */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Notification list */}
          <div className={`overflow-y-auto space-y-1 p-3 min-h-0 ${selectedNotification ? "w-1/2 border-r border-border" : "w-full"}`}>
            {isLoadingAll ? (
              <NotificationLoading />
            ) : filtered.length === 0 ? (
              <NotificationEmptyState filter={filter} />
            ) : (
              filtered.map((n) => (
                <NotificationCard
                  key={n.id}
                  notification={n}
                  onClick={handleClick}
                  onMarkRead={markAsRead}
                  showUserEmail={isAdmin}
                  isSuperAdmin={isSuperAdmin}
                  isSelected={selectedNotification?.id === n.id}
                />
              ))
            )}
          </div>

          {/* Detail panel */}
          {selectedNotification && (
            <div className="w-1/2 overflow-y-auto p-5">
              <NotificationDetail
                notification={selectedNotification}
                onNavigateToAutomation={handleNavigateToAutomation}
              />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------- Inline detail panel ----------

function NotificationDetail({
  notification,
  onNavigateToAutomation,
}: {
  notification: Notification;
  onNavigateToAutomation: (id: string) => void;
}) {
  return (
    <div className="space-y-5">
      {/* Title + severity */}
      <div>
        <h3 className="text-base font-semibold">{notification.title}</h3>
        <div className="flex items-center gap-2 mt-2">
          <Badge variant={SEVERITY_VARIANT[notification.severity] ?? "secondary"}>
            {notification.severity}
          </Badge>
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="size-3" />
            {new Date(notification.created_at).toLocaleString()}
          </span>
        </div>
      </div>

      {/* Message */}
      <div className="rounded-md border border-border/50 bg-muted/30 p-3">
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{notification.message}</p>
      </div>

      {/* Automation info */}
      {notification.automation_name && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Automation</h4>
          <div className="flex items-center gap-2 rounded-md border border-border/50 p-3">
            <Zap className="size-4 text-primary shrink-0" />
            <span className="text-sm font-medium flex-1 truncate">{notification.automation_name}</span>
            {notification.automation_id && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs shrink-0"
                onClick={() => onNavigateToAutomation(notification.automation_id!)}
              >
                <ExternalLink className="size-3 mr-1" />
                View Automation
              </Button>
            )}
          </div>
        </div>
      )}

      {/* User info (admin view) */}
      {notification.user_email && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">User</h4>
          <div className="flex items-center gap-2 flex-wrap text-sm">
            <span className="font-medium">{notification.user_email}</span>
            {notification.user_org_id && (
              <Badge variant="outline" className="text-[10px]">{notification.user_org_id}</Badge>
            )}
            {notification.user_is_admin !== undefined && (
              <Badge variant={notification.user_is_admin ? "default" : "secondary"} className="text-[10px]">
                {notification.user_is_admin ? "admin" : "user"}
              </Badge>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
