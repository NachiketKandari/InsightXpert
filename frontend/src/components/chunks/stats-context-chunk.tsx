"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronRight, BarChart3 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface StatsContextChunkProps {
  content: string;
  groups?: string[];
}

function StatsContextChunkInner({ content, groups }: StatsContextChunkProps) {
  const [open, setOpen] = useState(false);

  const subtitle = groups?.length
    ? groups.map((g) => g.replace(/_/g, " ")).join(", ")
    : "Pre-computed statistics";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-lg border border-border bg-card/50 overflow-hidden">
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-2 w-full px-3 py-2 hover:bg-accent/30 transition-colors text-left">
            <ChevronRight
              className={cn(
                "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
                open && "rotate-90",
              )}
            />
            <BarChart3 className="size-4 shrink-0 text-muted-foreground" />
            <Badge variant="secondary" className="text-xs">
              Data Source
            </Badge>
            <span className="text-xs text-muted-foreground truncate">
              {subtitle}
            </span>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-3 border-t border-border/50 pt-3 prose-invert prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h3: ({ children }) => (
                  <h3 className="text-sm font-semibold text-foreground mt-2 mb-1">
                    {children}
                  </h3>
                ),
                p: ({ children }) => (
                  <p className="text-xs text-foreground/90 leading-relaxed mb-1">
                    {children}
                  </p>
                ),
                ul: ({ children }) => (
                  <ul className="text-xs text-foreground/90 list-disc list-inside space-y-0.5 mb-1">
                    {children}
                  </ul>
                ),
                li: ({ children }) => (
                  <li className="leading-relaxed">{children}</li>
                ),
                strong: ({ children }) => (
                  <strong className="font-semibold text-foreground">
                    {children}
                  </strong>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-1.5 rounded-lg border border-border">
                    <table className="w-full text-xs">{children}</table>
                  </div>
                ),
                thead: ({ children }) => (
                  <thead className="bg-muted/50">{children}</thead>
                ),
                th: ({ children }) => (
                  <th className="px-2 py-1.5 text-left text-xs font-medium text-muted-foreground">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="px-2 py-1 text-xs font-mono border-t border-border">
                    {children}
                  </td>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export const StatsContextChunk = React.memo(StatsContextChunkInner);
