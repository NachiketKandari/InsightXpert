"use client";

import React from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import type { EnrichmentTrace } from "@/types/chat";

interface CitationLinkProps {
  sourceIndex: number;
  trace: EnrichmentTrace;
  onClick: (sourceIndex: number) => void;
}

export const CitationLink = React.memo(function CitationLink({
  sourceIndex,
  trace,
  onClick,
}: CitationLinkProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => onClick(sourceIndex)}
          className="inline-flex items-center justify-center min-w-[1.25rem] h-4 px-1 text-[10px] font-semibold leading-none text-primary bg-primary/10 hover:bg-primary/20 rounded-full cursor-pointer transition-colors align-super translate-y-[-2px] mx-[1px]"
        >
          {sourceIndex}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs p-3">
        <div className="space-y-1.5">
          <Badge variant="secondary" className="text-[10px]">
            {trace.category}
          </Badge>
          <p className="text-xs font-medium">{trace.question}</p>
          {trace.final_answer && (
            <p className="text-xs text-muted-foreground line-clamp-3">
              {trace.final_answer.slice(0, 200)}
              {trace.final_answer.length > 200 ? "\u2026" : ""}
            </p>
          )}
          <p className="text-[10px] text-muted-foreground/70">
            Click for full trace
          </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
});
