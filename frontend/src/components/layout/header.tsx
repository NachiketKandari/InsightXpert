"use client";

import React from "react";
import { Menu, TerminalSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { useIsMobile } from "@/hooks/use-media-query";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { AppLogo } from "@/components/ui/app-logo";
import { useClientConfigStore } from "@/stores/client-config-store";
import { useClientConfig } from "@/hooks/use-client-config";
import { DatasetSelector } from "./dataset-selector";
import { NotificationBell } from "@/components/notifications/notification-bell";

export const Header = React.memo(function Header() {
  const isMobile = useIsMobile();
  const leftOpen = useChatStore((s) => s.leftSidebarOpen);
  const toggleLeftSidebar = useChatStore((s) => s.toggleLeftSidebar);
  const sqlExecutorOpen = useChatStore((s) => s.sqlExecutorOpen);
  const setSqlExecutorOpen = useChatStore((s) => s.setSqlExecutorOpen);
  const displayName = useClientConfigStore((s) => s.config?.branding?.display_name);
  const { isFeatureEnabled } = useClientConfig();
  const showSqlExecutor = isFeatureEnabled("sql_executor");

  return (
    <header className="relative z-50 h-14 shrink-0 flex items-center justify-between px-3 sm:px-4 glass border-b border-border">
      <div className="flex items-center gap-2">
        {isMobile && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-9"
                onClick={toggleLeftSidebar}
                aria-label="Chat history"
                aria-expanded={leftOpen}
              >
                <Menu className="size-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Chat history</TooltipContent>
          </Tooltip>
        )}
        <AppLogo className="size-7" />
        <span className="text-lg font-semibold tracking-tight hidden md:inline">
          {displayName || (<>Insight<span className="text-primary dark:text-cyan-accent">Xpert</span></>)}
        </span>
        <div className="hidden md:flex ml-1 rounded-md bg-black/5 dark:bg-white/5 px-0.5 py-0.5">
          <DatasetSelector />
        </div>
      </div>
      <div className="flex items-center gap-2">
        {showSqlExecutor && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-9"
                onClick={() => setSqlExecutorOpen(!sqlExecutorOpen)}
                aria-label="SQL Executor"
                aria-expanded={sqlExecutorOpen}
              >
                <TerminalSquare className="size-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">SQL Executor</TooltipContent>
          </Tooltip>
        )}
        <NotificationBell />
      </div>
    </header>
  );
});
