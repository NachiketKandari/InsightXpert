"use client";

import { useState } from "react";
import { ChevronRight, Table2 } from "lucide-react";
import type { ChatChunk } from "@/types/chat";
import { parseToolResult } from "@/lib/chunk-parser";
import { DataTable } from "./data-table";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface ToolResultChunkProps {
  chunk: ChatChunk;
}

export function ToolResultChunk({ chunk }: ToolResultChunkProps) {
  const parsed = parseToolResult(chunk);
  const [open, setOpen] = useState(true);

  if (!parsed) {
    const raw =
      typeof chunk.data?.result === "string"
        ? chunk.data.result
        : JSON.stringify(chunk.data, null, 2);

    return (
      <pre className="text-xs text-muted-foreground bg-muted/30 rounded-lg p-3 font-mono overflow-x-auto">
        {raw}
      </pre>
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-lg border border-border bg-card/50 overflow-hidden">
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-2 w-full px-3 py-2 hover:bg-accent/30 transition-colors text-left">
            <ChevronRight
              className={cn(
                "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
                open && "rotate-90"
              )}
            />
            <Table2 className="size-4 shrink-0 text-muted-foreground" />
            <Badge variant="secondary" className="text-xs">
              Query Results
            </Badge>
            <span className="text-xs text-muted-foreground">
              {parsed.rowCount} row{parsed.rowCount !== 1 ? "s" : ""}
            </span>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-3 border-t border-border/50 pt-3">
            <DataTable columns={parsed.columns} rows={parsed.rows} />
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
