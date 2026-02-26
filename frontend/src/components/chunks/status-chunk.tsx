"use client";

import { useState } from "react";
import { CheckCircle, ChevronRight, Loader2 } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface StatusChunkProps {
  content: string;
  isComplete?: boolean;
  ragContext?: string[];
}

export function StatusChunk({ content, isComplete, ragContext }: StatusChunkProps) {
  const [open, setOpen] = useState(false);
  const hasRag = ragContext && ragContext.length > 0;

  if (!hasRag) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-sm py-1">
        {isComplete ? (
          <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
        ) : (
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
        )}
        <span>{content}</span>
      </div>
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex items-center gap-2 text-muted-foreground text-sm py-1 w-full text-left hover:text-foreground transition-colors group">
          {isComplete ? (
            <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
          ) : (
            <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
          )}
          <span className="flex-1">{content}</span>
          <ChevronRight
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-transform duration-150 opacity-50 group-hover:opacity-100",
              open && "rotate-90"
            )}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-1 ml-5 space-y-1 border-l border-border/50 pl-3 pb-1">
          {ragContext.map((q, i) => (
            <li key={i} className="text-xs text-muted-foreground/70 truncate" title={q}>
              {q}
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
