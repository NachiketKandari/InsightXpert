"use client";

import React, { useState, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { CitationLink } from "./citation-link";
import { TraceModal } from "./trace-modal";
import type { EnrichmentTrace } from "@/types/chat";

interface InsightChunkProps {
  content: string;
  traces: EnrichmentTrace[];
}

// Regex to match [[N]] citation markers
const CITATION_RE = /\[\[(\d+)\]\]/g;

// Section headers the response_generator.j2 produces (case-insensitive match).
// The first two are "primary" (always visible), the rest are "secondary" (collapsible).
const PRIMARY_SECTIONS = ["direct answer", "key evidence"];
const SECONDARY_SECTIONS = [
  "contextual analysis",
  "root-cause hypothesis",
  "root cause hypothesis",
  "business recommendations",
  "follow-up questions",
  "follow up questions",
  "caveats",
];

interface ParsedSection {
  title: string;
  content: string;
  isPrimary: boolean;
}

/**
 * Split insight markdown into named sections based on ## or **N.** header patterns.
 * Returns { preamble, sections[] }. Preamble is any text before the first header.
 */
function parseSections(markdown: string): { preamble: string; sections: ParsedSection[] } {
  // Match headers like:
  //   ## Direct Answer        (h2)
  //   **Direct Answer**       (bold line)
  //   1. **Direct Answer**    (numbered bold)
  //   **1. Direct Answer**    (bold with number inside)
  const headerRe = /^(?:#{1,3}\s+(?:\d+\.\s*)?(.+)|(?:\d+\.\s*)?\*\*(.+?)\*\*\s*(?:[-—:].*)?)\s*$/gm;

  const matches: { title: string; index: number }[] = [];
  let m: RegExpExecArray | null;

  while ((m = headerRe.exec(markdown)) !== null) {
    const raw = (m[1] || m[2] || "").trim();
    // Strip leading numbers like "1. " and trailing punctuation
    const title = raw.replace(/^\d+\.\s*/, "").replace(/[-—:]+$/, "").trim();
    matches.push({ title, index: m.index });
  }

  if (matches.length === 0) {
    return { preamble: markdown, sections: [] };
  }

  const preamble = markdown.slice(0, matches[0].index).trim();
  const sections: ParsedSection[] = [];

  const allKnown = [...PRIMARY_SECTIONS, ...SECONDARY_SECTIONS];

  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index;
    const end = i + 1 < matches.length ? matches[i + 1].index : markdown.length;
    const sectionText = markdown.slice(start, end);

    // Remove the header line itself from the content
    const firstNewline = sectionText.indexOf("\n");
    const body = firstNewline >= 0 ? sectionText.slice(firstNewline + 1).trim() : "";

    const titleLower = matches[i].title.toLowerCase();
    const isPrimary = PRIMARY_SECTIONS.some((s) => titleLower.includes(s));
    const isKnown = allKnown.some((s) => titleLower.includes(s));

    // Unknown sections get treated as primary (safe default — show them)
    sections.push({
      title: matches[i].title,
      content: body,
      isPrimary: isPrimary || !isKnown,
    });
  }

  return { preamble, sections };
}

function processCitations(
  children: React.ReactNode,
  traceMap: Map<number, EnrichmentTrace>,
  onCitationClick: (idx: number) => void,
): React.ReactNode[] {
  const result: React.ReactNode[] = [];

  React.Children.forEach(children, (child) => {
    if (typeof child !== "string") {
      result.push(child);
      return;
    }

    let lastIndex = 0;
    let match: RegExpExecArray | null;
    const re = new RegExp(CITATION_RE.source, "g");

    while ((match = re.exec(child)) !== null) {
      if (match.index > lastIndex) {
        result.push(child.slice(lastIndex, match.index));
      }

      const sourceIdx = parseInt(match[1], 10);
      const trace = traceMap.get(sourceIdx);

      if (trace) {
        result.push(
          <CitationLink
            key={`cite-${match.index}-${sourceIdx}`}
            sourceIndex={sourceIdx}
            trace={trace}
            onClick={onCitationClick}
          />,
        );
      } else {
        result.push(match[0]);
      }

      lastIndex = re.lastIndex;
    }

    if (lastIndex < child.length) {
      result.push(child.slice(lastIndex));
    }
  });

  return result;
}

/** Shared markdown component config for rendering insight sections. */
function InsightMarkdown({
  content,
  traceMap,
  onCitationClick,
}: {
  content: string;
  traceMap: Map<number, EnrichmentTrace>;
  onCitationClick: (idx: number) => void;
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => (
          <h1 className="text-lg font-bold text-foreground mt-4 mb-2">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-base font-semibold text-foreground mt-3 mb-2">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-semibold text-foreground mt-2 mb-1">{children}</h3>
        ),
        p: ({ children }) => (
          <p className="text-sm text-foreground/90 leading-relaxed mb-2">
            {processCitations(children, traceMap, onCitationClick)}
          </p>
        ),
        ul: ({ children }) => (
          <ul className="text-sm text-foreground/90 list-disc list-inside space-y-1 mb-2">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="text-sm text-foreground/90 list-decimal list-inside space-y-1 mb-2">
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed">
            {processCitations(children, traceMap, onCitationClick)}
          </li>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-foreground">{children}</strong>
        ),
        code: ({ children, className }) => {
          const isInline = !className;
          if (isInline) {
            return (
              <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono text-primary">
                {children}
              </code>
            );
          }
          return (
            <code className="block bg-muted p-3 rounded-lg text-xs font-mono overflow-x-auto my-2">
              {children}
            </code>
          );
        },
        pre: ({ children }) => (
          <pre className="bg-muted rounded-lg overflow-x-auto my-2">{children}</pre>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2 rounded-lg border border-border">
            <table className="w-full text-sm">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-muted/50">{children}</thead>,
        th: ({ children }) => (
          <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 text-xs font-mono border-t border-border">{children}</td>
        ),
        a: ({ children, href }) => (
          <a
            href={href}
            className="text-primary underline underline-offset-2 hover:text-primary/80"
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-primary/50 pl-3 text-sm text-muted-foreground italic my-2">
            {children}
          </blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/** Collapsible section for secondary insight content. */
function CollapsibleSection({
  title,
  content,
  traceMap,
  onCitationClick,
}: {
  title: string;
  content: string;
  traceMap: Map<number, EnrichmentTrace>;
  onCitationClick: (idx: number) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-left text-sm transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800/50 dark:hover:bg-zinc-800">
        {isOpen ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
        )}
        <span className="font-medium text-zinc-700 dark:text-zinc-300 text-sm">
          {title}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-3 pt-2 pb-1">
          <InsightMarkdown
            content={content}
            traceMap={traceMap}
            onCitationClick={onCitationClick}
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export const InsightChunk = React.memo(function InsightChunk({
  content,
  traces,
}: InsightChunkProps) {
  const [activeTraceIdx, setActiveTraceIdx] = useState<number | null>(null);

  const traceMap = useMemo(() => {
    const m = new Map<number, EnrichmentTrace>();
    for (const t of traces) m.set(t.source_index, t);
    return m;
  }, [traces]);

  const handleCitationClick = useCallback((idx: number) => {
    setActiveTraceIdx(idx);
  }, []);

  const activeTrace = activeTraceIdx != null ? traceMap.get(activeTraceIdx) ?? null : null;

  const { preamble, sections } = useMemo(() => parseSections(content), [content]);
  const primarySections = sections.filter((s) => s.isPrimary);
  const secondarySections = sections.filter((s) => !s.isPrimary);

  // If parsing found no sections, fall back to rendering everything as primary
  const hasSections = sections.length > 0;

  return (
    <>
      <div className="prose-invert prose-sm max-w-none">
        {hasSections ? (
          <div className="space-y-3">
            {/* Preamble (text before any section header) */}
            {preamble && (
              <InsightMarkdown
                content={preamble}
                traceMap={traceMap}
                onCitationClick={handleCitationClick}
              />
            )}

            {/* Primary sections: always visible */}
            {primarySections.map((section, i) => (
              <div key={`primary-${i}`}>
                <h3 className="text-sm font-semibold text-foreground mt-2 mb-1.5">
                  {section.title}
                </h3>
                <InsightMarkdown
                  content={section.content}
                  traceMap={traceMap}
                  onCitationClick={handleCitationClick}
                />
              </div>
            ))}

            {/* Secondary sections: collapsible */}
            {secondarySections.length > 0 && (
              <div className="space-y-2 mt-2">
                {secondarySections.map((section, i) => (
                  <CollapsibleSection
                    key={`secondary-${i}`}
                    title={section.title}
                    content={section.content}
                    traceMap={traceMap}
                    onCitationClick={handleCitationClick}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          /* Fallback: no sections detected, render everything */
          <InsightMarkdown
            content={content}
            traceMap={traceMap}
            onCitationClick={handleCitationClick}
          />
        )}
      </div>

      <TraceModal
        trace={activeTrace}
        open={activeTraceIdx != null}
        onOpenChange={(isOpen) => {
          if (!isOpen) setActiveTraceIdx(null);
        }}
      />
    </>
  );
});
