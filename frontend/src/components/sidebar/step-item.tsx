"use client";

import { useState } from "react";
import { Circle, CheckCircle, XCircle, Loader2, ChevronRight } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { AgentStep } from "@/types/chat";
import { cn } from "@/lib/utils";

interface StepItemProps {
  step: AgentStep;
}

const statusIcon: Record<AgentStep["status"], React.ReactNode> = {
  pending: <Circle className="size-3.5 text-muted-foreground" />,
  running: <Loader2 className="size-3.5 text-cyan-accent animate-spin" />,
  done: <CheckCircle className="size-3.5 text-emerald-500" />,
  error: <XCircle className="size-3.5 text-destructive" />,
};

export function StepItem({ step }: StepItemProps) {
  const [open, setOpen] = useState(false);
  const hasDetail = !!(step.sql || step.detail || step.resultPreview || step.toolName);

  if (!hasDetail) {
    return (
      <div className="flex items-center gap-2.5 px-3 py-1.5 min-w-0 max-w-full overflow-hidden">
        <div className="shrink-0">{statusIcon[step.status]}</div>
        <p className="text-xs leading-tight truncate flex-1 min-w-0" title={step.label}>
          {step.label}
        </p>
      </div>
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2.5 px-3 py-1.5 min-w-0 max-w-full overflow-hidden w-full text-left hover:bg-accent/30 rounded-md transition-colors group">
          <div className="shrink-0">{statusIcon[step.status]}</div>
          <p className="text-xs leading-tight truncate flex-1 min-w-0" title={step.label}>
            {step.label}
          </p>
          <ChevronRight
            className={cn(
              "size-3 shrink-0 text-muted-foreground transition-transform duration-200",
              open && "rotate-90"
            )}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="ml-6 mr-3 mb-2 space-y-1.5 overflow-hidden">
          {step.toolName && (
            <p className="text-[11px] text-muted-foreground">
              Tool: <span className="text-foreground/80 font-mono">{step.toolName}</span>
            </p>
          )}
          {step.sql && (
            <div className="rounded bg-muted/40 border border-border/50 overflow-hidden">
              <pre className="text-[11px] font-mono p-2 overflow-x-auto text-foreground/80 whitespace-pre-wrap break-all">
                {step.sql}
              </pre>
            </div>
          )}
          {step.resultPreview && (
            <p className="text-[11px] text-muted-foreground truncate" title={step.resultPreview}>
              {step.resultPreview}
            </p>
          )}
          {step.detail && !step.sql && (
            <p className="text-[11px] text-muted-foreground truncate" title={step.detail}>
              {step.detail}
            </p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
