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
        <div className="flex items-center gap-2">
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
          <span className="text-lg font-semibold tracking-tight">
            Insight<span className="text-cyan-accent">Xpert</span>
          </span>
        </div>

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
