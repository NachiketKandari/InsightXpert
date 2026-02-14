"use client";

import { useState } from "react";
import { TerminalSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { SqlExecutor } from "@/components/sql/sql-executor";
import { ModelSelector } from "./model-selector";
import { UserMenu } from "./user-menu";

export function Header() {
  const [sqlOpen, setSqlOpen] = useState(false);

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

          <UserMenu />
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
