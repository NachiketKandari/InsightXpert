"use client";

import { Loader2 } from "lucide-react";

interface StatusChunkProps {
  content: string;
}

export function StatusChunk({ content }: StatusChunkProps) {
  return (
    <div className="flex items-center gap-2 text-muted-foreground text-sm py-1">
      <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
      <span>{content}</span>
    </div>
  );
}
