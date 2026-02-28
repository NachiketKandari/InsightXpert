"use client";

import React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogOut, Activity, Sun, Moon, Settings, ListChecks, ChevronsUpDown, Zap } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { useClientConfig } from "@/hooks/use-client-config";
import { useChatStore } from "@/stores/chat-store";
import { useIsMobile } from "@/hooks/use-media-query";
import { useTheme } from "@/hooks/use-theme";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";

function getInitials(email: string): string {
  const local = email.split("@")[0] ?? "";
  // Try splitting on common separators (dot, underscore, hyphen)
  const parts = local.split(/[._-]/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

function getDisplayName(email: string): string {
  const local = email.split("@")[0] ?? "";
  return local
    .split(/[._-]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export const UserMenu = React.memo(function UserMenu() {
  const { user, logout } = useAuthStore();
  const { isAdmin, config } = useClientConfig();
  const router = useRouter();
  const isMobile = useIsMobile();
  const toggleRightSidebar = useChatStore((s) => s.toggleRightSidebar);
  const { theme, toggle: toggleTheme } = useTheme();
  const setSampleQuestionsOpen = useChatStore((s) => s.setSampleQuestionsOpen);

  if (!user) return null;

  const initials = getInitials(user.email);
  const displayName = getDisplayName(user.email);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="border-t border-border">
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-2 px-4 py-3 w-full cursor-pointer hover:bg-accent/50 dark:hover:bg-accent/30 transition-colors outline-none">
                <Avatar size="default">
                  <AvatarFallback className="bg-primary/15 text-primary dark:bg-cyan-accent/15 dark:text-cyan-accent text-xs font-semibold">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-sm font-medium leading-none truncate">{displayName}</p>
                  <p className="text-xs text-muted-foreground leading-none mt-1 truncate">
                    {user.email}
                  </p>
                </div>
                <ChevronsUpDown className="size-4 text-muted-foreground shrink-0" />
              </button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="top">Account options</TooltipContent>
        </Tooltip>
        <DropdownMenuContent side="top" align="center" className="w-[284px] mb-1">
          <DropdownMenuLabel className="font-normal">
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium leading-none">{displayName}</p>
              <p className="text-xs text-muted-foreground leading-none">
                {user.email}
              </p>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {isMobile && (
            <>
              <DropdownMenuItem onClick={toggleRightSidebar}>
                <Activity className="size-4" />
                Agent Process
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          )}
          {isAdmin && (
            <DropdownMenuItem asChild>
              <Link href="/admin">
                <Settings className="size-4" />
                Admin Panel
              </Link>
            </DropdownMenuItem>
          )}
          {isAdmin && (
            <DropdownMenuItem asChild>
              <Link href="/admin/automations">
                <Zap className="size-4" />
                Automations
              </Link>
            </DropdownMenuItem>
          )}
<DropdownMenuItem onClick={() => setSampleQuestionsOpen(true)}>
            <ListChecks className="size-4" />
            Sample Questions
          </DropdownMenuItem>
          {!config?.branding?.color_mode && (
            <DropdownMenuItem onClick={toggleTheme}>
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
              {theme === "dark" ? "Light Mode" : "Dark Mode"}
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout} variant="destructive">
            <LogOut className="size-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
});
