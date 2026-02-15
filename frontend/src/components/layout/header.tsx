"use client";

import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserMenu } from "./user-menu";
import { useChatStore } from "@/stores/chat-store";
import { useIsMobile } from "@/hooks/use-media-query";

export function Header() {
  const isMobile = useIsMobile();
  const leftOpen = useChatStore((s) => s.leftSidebarOpen);
  const toggleLeftSidebar = useChatStore((s) => s.toggleLeftSidebar);

  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-3 sm:px-4 glass border-b border-border">
      <div className="flex items-center gap-2">
        {isMobile && (
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
        )}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 512 512"
          className="size-7"
          aria-hidden="true"
        >
          <rect width="512" height="512" rx="108" fill="#0B1120" />
          <rect x="100" y="312" width="72" height="120" rx="10" fill="#06B6D4" opacity="0.55" />
          <rect x="220" y="216" width="72" height="216" rx="10" fill="#06B6D4" opacity="0.75" />
          <rect x="340" y="120" width="72" height="312" rx="10" fill="#06B6D4" />
          <polyline points="136,312 256,216 376,120" fill="none" stroke="#06B6D4" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="376" cy="120" r="18" fill="#fff" opacity="0.9" />
          <circle cx="376" cy="120" r="10" fill="#06B6D4" />
        </svg>
        <span className="text-lg font-semibold tracking-tight hidden md:inline">
          Insight<span className="text-primary dark:text-cyan-accent">Xpert</span>
        </span>
      </div>

      <div className="flex items-center gap-1 md:gap-2">
        <UserMenu />
      </div>
    </header>
  );
}
