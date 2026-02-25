"use client";

import { useState } from "react";
import {
  Circle,
  CheckCircle,
  XCircle,
  Loader2,
  ChevronRight,
  Copy,
  Check,
  Brain,
  Database,
  TableProperties,
  FileText,
  BookOpen,
} from "lucide-react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import sqlLang from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import json from "react-syntax-highlighter/dist/esm/languages/hljs/json";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { AgentStep } from "@/types/chat";
import { cn } from "@/lib/utils";
import { useTheme } from "@/hooks/use-theme";
import { useSyntaxTheme } from "@/hooks/use-syntax-theme";

SyntaxHighlighter.registerLanguage("sql", sqlLang);
SyntaxHighlighter.registerLanguage("json", json);

interface StepItemProps {
  step: AgentStep;
}

const statusIcon: Record<AgentStep["status"], React.ReactNode> = {
  pending: <Circle className="size-3.5 text-muted-foreground" />,
  running: <Loader2 className="size-3.5 text-cyan-accent animate-spin" />,
  done: <CheckCircle className="size-3.5 text-emerald-500" />,
  error: <XCircle className="size-3.5 text-destructive" />,
};

const highlighterStyle = {
  background: "transparent",
  padding: "0.5rem 0",
  margin: 0,
  fontSize: "0.7rem",
  lineHeight: "1.4",
  fontFamily: "var(--font-mono)",
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="text-muted-foreground hover:text-foreground transition-colors p-0.5 rounded hover:bg-accent/50"
      aria-label="Copy"
    >
      {copied ? (
        <Check className="size-3 text-emerald-400" />
      ) : (
        <Copy className="size-3" />
      )}
    </button>
  );
}

function SectionHeader({
  icon,
  label,
  copyText,
}: {
  icon: React.ReactNode;
  label: string;
  copyText?: string;
}) {
  return (
    <div className="flex items-center gap-1.5 mb-1">
      {icon}
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {copyText && (
        <span className="ml-auto">
          <CopyButton text={copyText} />
        </span>
      )}
    </div>
  );
}

function formatResultData(raw: string): string | null {
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null) {
      return JSON.stringify(parsed, null, 2);
    }
    return raw;
  } catch {
    return raw;
  }
}

export function StepItem({ step }: StepItemProps) {
  const [open, setOpen] = useState(false);
  const { theme } = useTheme();
  const syntaxTheme = useSyntaxTheme();

  const hasDetail = !!(
    step.sql ||
    step.detail ||
    step.resultPreview ||
    step.toolName ||
    step.llmReasoning ||
    step.toolArgs ||
    step.resultData ||
    step.ragContext
  );

  if (!hasDetail) {
    return (
      <div className="flex items-center gap-2.5 px-3 py-1.5 min-w-0 max-w-full overflow-hidden">
        <div className="shrink-0">{statusIcon[step.status]}</div>
        <p
          className="text-xs leading-tight truncate flex-1 min-w-0"
          title={step.label}
        >
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
          <p
            className="text-xs leading-tight truncate flex-1 min-w-0"
            title={step.label}
          >
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
        <div className="ml-6 mr-2 mb-2 space-y-2 overflow-hidden">
          {/* RAG context — similar query titles */}
          {step.ragContext && step.ragContext.length > 0 && (
            <div className="rounded-md border border-amber-500/20 dark:border-amber-400/20 bg-amber-500/5 dark:bg-amber-400/5 overflow-hidden">
              <div className="px-2 pt-1.5">
                <SectionHeader
                  icon={<BookOpen className="size-3 text-amber-600 dark:text-amber-400" />}
                  label="Retrieved Context"
                />
              </div>
              <ul className="px-2 pb-2 space-y-0.5">
                {step.ragContext.map((title, i) => (
                  <li
                    key={i}
                    className="text-[11px] leading-relaxed text-foreground/70 flex items-start gap-1.5"
                  >
                    <span className="text-amber-600/60 dark:text-amber-400/60 shrink-0 mt-px">
                      &bull;
                    </span>
                    <span className="min-w-0 break-words">{title}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tool name badge */}
          {step.toolName && (
            <div className="flex items-center gap-1.5">
              <span className={cn(
                "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-mono",
                theme === "dark"
                  ? "bg-cyan-accent/15 border-cyan-accent/30 text-cyan-accent"
                  : "bg-teal-700/10 border-teal-700/25 text-teal-700"
              )}>
                <Database className="size-2.5" />
                {step.toolName}
              </span>
            </div>
          )}

          {/* LLM reasoning */}
          {step.llmReasoning && (
            <div className="rounded-md border border-violet-500/20 bg-violet-500/5 overflow-hidden">
              <SectionHeader
                icon={<Brain className="size-3 text-violet-600 dark:text-violet-400" />}
                label="LLM Reasoning"
              />
              <p className="text-[11px] leading-relaxed text-foreground/70 px-2 pb-2 whitespace-pre-wrap">
                {step.llmReasoning}
              </p>
            </div>
          )}

          {/* SQL query with syntax highlighting */}
          {step.sql && (
            <div className={cn(
              "rounded-md border overflow-hidden",
              theme === "dark"
                ? "border-cyan-accent/30 bg-cyan-accent/8"
                : "border-teal-700/25 bg-teal-700/8"
            )}>
              <div className="px-2 pt-1.5">
                <SectionHeader
                  icon={<Database className={cn("size-3", theme === "dark" ? "text-cyan-accent" : "text-teal-700")} />}
                  label="SQL Query"
                  copyText={step.sql}
                />
              </div>
              <div className="px-2 pb-1">
                <SyntaxHighlighter
                  language="sql"
                  style={syntaxTheme}
                  customStyle={highlighterStyle}
                  wrapLongLines
                >
                  {step.sql}
                </SyntaxHighlighter>
              </div>
            </div>
          )}

          {/* Result preview */}
          {step.resultPreview && (
            <div className={cn("flex items-center gap-1.5 text-[11px]", theme === "dark" ? "text-emerald-400/80" : "text-emerald-600/80")}>
              <TableProperties className="size-3" />
              <span>{step.resultPreview}</span>
            </div>
          )}

          {/* Full result data */}
          {step.resultData && (
            <div className={cn(
              "rounded-md border overflow-hidden",
              theme === "dark"
                ? "border-emerald-400/30 bg-emerald-400/8"
                : "border-emerald-700/25 bg-emerald-700/10"
            )}>
              <div className="px-2 pt-1.5">
                <SectionHeader
                  icon={<TableProperties className={cn("size-3", theme === "dark" ? "text-emerald-400" : "text-emerald-700")} />}
                  label="Result Data"
                  copyText={step.resultData}
                />
              </div>
              <div className="px-2 pb-1 max-h-48 overflow-auto">
                <SyntaxHighlighter
                  language="json"
                  style={syntaxTheme}
                  customStyle={highlighterStyle}
                  wrapLongLines
                >
                  {formatResultData(step.resultData) || step.resultData}
                </SyntaxHighlighter>
              </div>
            </div>
          )}

          {/* Answer / detail text */}
          {step.detail && !step.sql && (
            <div className="rounded-md border border-border/50 bg-muted/30 overflow-hidden">
              <div className="px-2 pt-1.5">
                <SectionHeader
                  icon={<FileText className="size-3 text-muted-foreground" />}
                  label="Output"
                />
              </div>
              <p className="text-[11px] leading-relaxed text-foreground/70 px-2 pb-2 whitespace-pre-wrap max-h-64 overflow-auto">
                {step.detail}
              </p>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
