"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogOut, EllipsisVertical, Activity, Sun, Moon, Settings } from "lucide-react";
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

export function UserMenu() {
  const { user, logout } = useAuthStore();
  const { isAdmin } = useClientConfig();
  const router = useRouter();
  const isMobile = useIsMobile();
  const toggleRightSidebar = useChatStore((s) => s.toggleRightSidebar);
  const { theme, toggle: toggleTheme } = useTheme();

  if (!user) return null;

  const initials = getInitials(user.email);
  const displayName = getDisplayName(user.email);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="flex items-center gap-0.5 ml-1 pl-2 border-l border-border">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="inline-flex items-center gap-1.5 rounded-full py-1 pl-1 pr-1.5 text-muted-foreground hover:bg-muted/50 transition-colors outline-none cursor-pointer">
            <Avatar size="sm">
              <AvatarFallback className="bg-primary/15 text-primary dark:bg-cyan-accent/15 dark:text-cyan-accent text-[10px] font-semibold">
                {initials}
              </AvatarFallback>
            </Avatar>
            <EllipsisVertical className="size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
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
          <DropdownMenuItem onClick={toggleTheme}>
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            {theme === "dark" ? "Light Mode" : "Dark Mode"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout} variant="destructive">
            <LogOut className="size-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
