"use client";

import { CheckCircle } from "lucide-react";

interface ToolCallChunkProps {
  content: string;
  isComplete?: boolean;
}

export function ToolCallChunk({ content, isComplete }: ToolCallChunkProps) {
  return (
    <div className="flex items-center gap-2 text-muted-foreground text-xs py-1">
      {isComplete ? (
        <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
      ) : (
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-accent opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-accent" />
        </span>
      )}
      <span>{content}</span>
    </div>
  );
}
