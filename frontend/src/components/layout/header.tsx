"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, TerminalSquare } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { SqlExecutor } from "@/components/sql/sql-executor";
import { ModelSelector } from "./model-selector";

export function Header() {
  const [sqlOpen, setSqlOpen] = useState(false);
  const { user, logout } = useAuthStore();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <>
      <header className="h-14 shrink-0 flex items-center justify-between px-4 glass border-b border-border">
        <span className="text-lg font-semibold tracking-tight">
          Insight<span className="text-cyan-accent">Xpert</span>
        </span>

        <div className="flex items-center gap-2">
          <ModelSelector />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={() => setSqlOpen(true)}
              >
                <TerminalSquare className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>SQL Executor</TooltipContent>
          </Tooltip>

          {user && (
            <div className="flex items-center gap-2 ml-1 pl-2 border-l border-border">
              <span className="text-sm text-muted-foreground hidden sm:inline">
                {user.email}
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8"
                    onClick={handleLogout}
                  >
                    <LogOut className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Sign out</TooltipContent>
              </Tooltip>
            </div>
          )}
        </div>
      </header>

      <Sheet open={sqlOpen} onOpenChange={setSqlOpen}>
        <SheetContent side="right" className="w-[560px] sm:w-[640px] p-0" showCloseButton={false}>
          <SheetTitle className="sr-only">SQL Executor</SheetTitle>
          <SqlExecutor onClose={() => setSqlOpen(false)} />
        </SheetContent>
      </Sheet>
    </>
  );
}
