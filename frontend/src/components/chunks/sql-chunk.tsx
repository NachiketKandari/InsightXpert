"use client";

import { useState } from "react";
import { Check, Copy, ChevronRight } from "lucide-react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import sql from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { useSyntaxTheme } from "@/hooks/use-syntax-theme";

SyntaxHighlighter.registerLanguage("sql", sql);

interface SqlChunkProps {
  sql: string;
}

export function SqlChunk({ sql: sqlCode }: SqlChunkProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const syntaxTheme = useSyntaxTheme();

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(sqlCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

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
            <Badge variant="secondary" className="text-xs">
              SQL Query
            </Badge>
            <span className="flex-1" />
            <span
              role="button"
              tabIndex={0}
              onClick={handleCopy}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCopy(e as unknown as React.MouseEvent);
              }}
              className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-accent"
              aria-label="Copy SQL"
            >
              {copied ? (
                <Check className="size-3.5 text-emerald-400" />
              ) : (
                <Copy className="size-3.5" />
              )}
            </span>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-3 border-t border-border/50">
            <SyntaxHighlighter
              language="sql"
              style={syntaxTheme}
              customStyle={{
                background: "transparent",
                padding: "0.75rem 0",
                margin: 0,
                fontSize: "0.8rem",
                fontFamily: "var(--font-mono)",
              }}
              wrapLongLines
            >
              {sqlCode}
            </SyntaxHighlighter>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
