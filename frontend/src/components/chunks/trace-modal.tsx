"use client";

import { useState, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import sqlLang from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import { useSyntaxTheme } from "@/hooks/use-syntax-theme";
import { DataTable } from "./data-table";
import {
  Database,
  Code,
  Brain,
  AlertCircle,
  Clock,
  ChevronRight,
  CheckCircle2,
  Table2,
} from "lucide-react";
import { CopyButton } from "@/components/ui/copy-button";
import type { EnrichmentTrace, TraceStep } from "@/types/chat";

SyntaxHighlighter.registerLanguage("sql", sqlLang);

interface TraceModalProps {
  trace: EnrichmentTrace | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Shared markdown renderer for LLM-generated content (reasoning, answers)
// ---------------------------------------------------------------------------
const mdComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="text-sm font-bold mt-3 mb-1.5 first:mt-0">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="text-xs font-semibold mt-2.5 mb-1">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-xs font-semibold mt-2 mb-0.5">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="text-xs leading-relaxed mb-1.5 last:mb-0">{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="text-xs list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="text-xs list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="text-xs leading-relaxed">{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  code: ({
    children,
    className,
  }: {
    children?: React.ReactNode;
    className?: string;
  }) => {
    if (className?.includes("language-")) {
      return <code className={`text-[11px] ${className}`}>{children}</code>;
    }
    return (
      <code className="bg-muted px-1 py-0.5 rounded text-[11px] font-mono">
        {children}
      </code>
    );
  },
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="bg-muted rounded-md overflow-x-auto mb-1.5 text-[11px]">
      {children}
    </pre>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="overflow-x-auto mb-1.5 rounded border border-border">
      <table className="w-full text-[11px]">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: React.ReactNode }) => (
    <thead className="bg-muted/50">{children}</thead>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="px-2 py-1 text-left text-[11px] font-medium text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="px-2 py-1 text-[11px] border-t border-border">{children}</td>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="border-l-2 border-primary/50 pl-2 text-xs text-muted-foreground italic my-1.5">
      {children}
    </blockquote>
  ),
};

function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
      {children}
    </ReactMarkdown>
  );
}

// ---------------------------------------------------------------------------
// Step helpers
// ---------------------------------------------------------------------------
const stepIcon = (type: string) => {
  switch (type) {
    case "sql":
    case "tool_result":
      return <Database className="h-3.5 w-3.5 text-blue-500" />;
    case "tool_call":
      return <Code className="h-3.5 w-3.5 text-violet-500" />;
    case "answer":
    case "insight":
      return <Brain className="h-3.5 w-3.5 text-emerald-500" />;
    case "error":
      return <AlertCircle className="h-3.5 w-3.5 text-red-500" />;
    default:
      return <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />;
  }
};

const stepLabel = (type: string) => {
  switch (type) {
    case "status":
      return "Processing";
    case "tool_call":
      return "Tool Call";
    case "sql":
      return "SQL Query";
    case "tool_result":
      return "Query Results";
    case "answer":
      return "Answer";
    case "insight":
      return "Insight";
    case "error":
      return "Error";
    default:
      return type;
  }
};

/** True for step types whose content is LLM-generated markdown. */
const isMarkdownStep = (type: string) =>
  type === "answer" || type === "insight" || type === "error";

// ---------------------------------------------------------------------------
// Reusable pieces
// ---------------------------------------------------------------------------
/** Try to parse result_data into columns + rows for DataTable. */
function parseResultTable(
  resultData: string | null | undefined,
): { columns: string[]; rows: Record<string, unknown>[] } | null {
  if (!resultData) return null;
  try {
    const parsed = JSON.parse(resultData);
    // Format: { columns: [...], rows: [...] }
    if (Array.isArray(parsed.rows) && parsed.rows.length > 0) {
      const columns: string[] =
        Array.isArray(parsed.columns) && parsed.columns.length > 0
          ? parsed.columns
          : Object.keys(parsed.rows[0]);
      return { columns, rows: parsed.rows };
    }
    // Format: plain array of objects
    if (Array.isArray(parsed) && parsed.length > 0 && typeof parsed[0] === "object") {
      return { columns: Object.keys(parsed[0]), rows: parsed };
    }
  } catch {
    /* not JSON */
  }
  return null;
}

function SqlBlock({ sql }: { sql: string }) {
  const syntaxTheme = useSyntaxTheme();

  return (
    <div className="rounded-md border border-border/50 bg-muted/30 overflow-hidden">
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/30">
        <span className="text-[10px] font-medium text-muted-foreground">SQL</span>
        <CopyButton text={sql} />
      </div>
      <SyntaxHighlighter
        language="sql"
        style={syntaxTheme}
        customStyle={{
          background: "transparent",
          padding: "0.5rem",
          margin: 0,
          fontSize: "0.75rem",
          fontFamily: "var(--font-mono)",
        }}
        wrapLongLines
      >
        {sql}
      </SyntaxHighlighter>
    </div>
  );
}

function ResultDataBlock({ step }: { step: TraceStep }) {
  const tableData = useMemo(() => parseResultTable(step.result_data), [step.result_data]);

  if (tableData) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Table2 className="h-3 w-3" />
          {tableData.rows.length} row{tableData.rows.length !== 1 ? "s" : ""} returned
        </div>
        <DataTable
          columns={tableData.columns}
          rows={tableData.rows}
          showRowNumbers
        />
      </div>
    );
  }

  // Fallback: try to extract row count from the raw preview, otherwise show
  // a compact summary instead of dumping raw JSON.
  if (step.result_preview) {
    let summary = step.result_preview;
    try {
      // Attempt partial parse to at least show a row count
      const match = step.result_preview.match(/"row_count"\s*:\s*(\d+)/);
      if (match) {
        summary = `Query returned ${match[1]} rows`;
      }
    } catch {
      /* keep original */
    }
    return (
      <p className="text-xs text-muted-foreground">
        {summary}
      </p>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// StepCard
// ---------------------------------------------------------------------------
function StepCard({ step }: { step: TraceStep }) {
  // Auto-open details for tool_result (the data table is the main content)
  const [open, setOpen] = useState(step.type === "tool_result");
  const hasDetail = step.sql || step.llm_reasoning || step.result_preview || step.result_data;

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="rounded-full border p-1.5 bg-background shrink-0">
          {stepIcon(step.type)}
        </div>
        <div className="flex-1 w-px bg-border" />
      </div>
      <div className="flex-1 pb-4 min-w-0">
        <div className="text-xs font-medium">{stepLabel(step.type)}</div>

        {/* Step content — render as markdown for answer/insight, plain text otherwise */}
        {step.content && (
          isMarkdownStep(step.type) ? (
            <div className="mt-0.5 text-muted-foreground">
              <Markdown>{step.content}</Markdown>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap break-words">
              {step.content}
            </p>
          )
        )}

        {step.tool_name && (
          <Badge variant="outline" className="text-[10px] mt-1">
            {step.tool_name}
          </Badge>
        )}

        {hasDetail && (
          <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger className="flex items-center gap-1 text-[11px] text-primary hover:underline mt-1 cursor-pointer">
              <ChevronRight
                className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
              />
              Details
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-1.5 space-y-2">
              {step.llm_reasoning && (
                <div className="bg-muted/50 rounded p-2">
                  <Markdown>{step.llm_reasoning}</Markdown>
                </div>
              )}
              {step.sql && <SqlBlock sql={step.sql} />}
              <ResultDataBlock step={step} />
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TraceModal
// ---------------------------------------------------------------------------
export function TraceModal({ trace, open, onOpenChange }: TraceModalProps) {
  if (!trace) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col gap-0 p-0">
        {/* Pinned header */}
        <DialogHeader className="shrink-0 border-b px-5 pt-5 pb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="secondary">{trace.category}</Badge>
            <Badge variant={trace.success ? "default" : "destructive"}>
              {trace.success ? "Success" : "Failed"}
            </Badge>
            {trace.duration_ms != null && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                {(trace.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
          </div>
          <DialogTitle className="text-sm">{trace.question}</DialogTitle>
          {trace.rationale && (
            <DialogDescription className="text-xs">
              {trace.rationale}
            </DialogDescription>
          )}
        </DialogHeader>

        {/* Scrollable body — timeline + final answer all scroll together */}
        <div className="flex-1 overflow-y-auto px-5 py-4 min-h-0">
          {trace.steps && trace.steps.length > 0 ? (
            <div>
              {trace.steps.map((step, i) => (
                <StepCard key={i} step={step} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground py-4 text-center">
              No trace steps recorded.
            </p>
          )}

        </div>
      </DialogContent>
    </Dialog>
  );
}
