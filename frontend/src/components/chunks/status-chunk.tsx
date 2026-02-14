"use client";

import { CheckCircle, Loader2 } from "lucide-react";

interface StatusChunkProps {
  content: string;
  isComplete?: boolean;
}

export function StatusChunk({ content, isComplete }: StatusChunkProps) {
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
