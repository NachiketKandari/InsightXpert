"use client";

import React, { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { CheckCircle, Loader2 } from "lucide-react";
import type { ChatChunk, EnrichmentTrace } from "@/types/chat";
import { parseToolResult } from "@/lib/chunk-parser";
import { detectChartType } from "@/lib/chart-detector";
import { VALID_CHART_TYPES } from "@/lib/constants";
import { StatusChunk } from "./status-chunk";
import { ToolCallChunk } from "./tool-call-chunk";
import { SqlChunk } from "./sql-chunk";
import { ToolResultChunk } from "./tool-result-chunk";
import { ChartBlock } from "./chart-block";
import { AnswerChunk } from "./answer-chunk";
import { InsightChunk } from "./insight-chunk";
import { ErrorChunk } from "./error-chunk";
import { ClarificationChunk } from "./clarification-chunk";
import { StatsContextChunk } from "./stats-context-chunk";

/** Inline progress step: spinner → checkmark after a brief delay during streaming. */
function ProgressStep({ label, isComplete }: { label: string; isComplete?: boolean }) {
  const [timerDone, setTimerDone] = useState(false);
  const done = (isComplete ?? false) || timerDone;

  useEffect(() => {
    if (isComplete) return;
    const timer = setTimeout(() => setTimerDone(true), 600);
    return () => clearTimeout(timer);
  }, [isComplete]);

  return (
    <div className="flex items-center gap-2 text-muted-foreground text-sm py-1">
      {done ? (
        <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
      ) : (
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
      )}
      <span>{label}</span>
    </div>
  );
}

interface ChunkRendererProps {
  chunk: ChatChunk;
  isComplete?: boolean;
  /** When true, charts render eagerly (no IntersectionObserver). */
  isStreaming?: boolean;
  enrichmentTraces?: EnrichmentTrace[];
}

function ChunkRendererInner({ chunk, isComplete, isStreaming, enrichmentTraces }: ChunkRendererProps) {
  const parsed = useMemo(
    () => (chunk.type === "tool_result" ? parseToolResult(chunk) : null),
    [chunk],
  );
  const suggestedChartType = chunk.type === "tool_result"
    ? ((chunk.data?.visualization as string) ?? null)
    : null;
  const xColumn = chunk.type === "tool_result"
    ? ((chunk.data?.x_column as string) ?? undefined)
    : undefined;
  const yColumn = chunk.type === "tool_result"
    ? ((chunk.data?.y_column as string) ?? undefined)
    : undefined;

  const willShowChart = useMemo(() => {
    if (!parsed) return false;
    const ct =
      suggestedChartType && VALID_CHART_TYPES.has(suggestedChartType)
        ? suggestedChartType
        : detectChartType(parsed.columns, parsed.rows);
    return ct !== "none" && ct !== "table";
  }, [parsed, suggestedChartType]);

  let content: React.ReactNode;

  switch (chunk.type) {
    case "status": {
      const rawRag = chunk.data?.rag_context;
      const ragContext = Array.isArray(rawRag) ? (rawRag as string[]) : undefined;
      content = <StatusChunk content={chunk.content ?? ""} isComplete={isComplete} ragContext={ragContext} />;
      break;
    }
    case "tool_call": {
      const toolLabel =
        chunk.tool_name === "run_sql"
          ? "Generating SQL query"
          : chunk.content ?? "";
      content = <ToolCallChunk content={toolLabel} isComplete={isComplete} />;
      break;
    }
    case "sql":
      content = chunk.sql ? <SqlChunk sql={chunk.sql} /> : null;
      break;
    case "tool_result":
      content = (
        <>
          <ToolResultChunk chunk={chunk} parsedData={parsed} />
          {willShowChart && parsed && (
            <>
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                <ProgressStep label="Creating visualization" />
              </motion.div>
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: "easeOut", delay: 0.7 }}
                className="mt-3"
              >
                <ChartBlock
                  columns={parsed.columns}
                  rows={parsed.rows}
                  suggestedChartType={suggestedChartType}
                  xColumn={xColumn}
                  yColumn={yColumn}
                  eager={isStreaming}
                />
              </motion.div>
            </>
          )}
        </>
      );
      break;
    case "answer":
      content = (
        <>
          <ProgressStep label="Generating answer" isComplete={isComplete} />
          <AnswerChunk content={chunk.content ?? ""} />
        </>
      );
      break;
    case "insight":
      content = (
        <>
          <ProgressStep label="Synthesized enriched insight" isComplete={isComplete} />
          {enrichmentTraces && enrichmentTraces.length > 0 ? (
            <InsightChunk content={chunk.content ?? ""} traces={enrichmentTraces} />
          ) : (
            <AnswerChunk content={chunk.content ?? ""} />
          )}
        </>
      );
      break;
    case "enrichment_trace":
      return null;
    case "error":
      content = <ErrorChunk content={chunk.content ?? "An error occurred"} />;
      break;
    case "clarification":
      content = (
        <ClarificationChunk
          content={chunk.content ?? "Could you clarify your question?"}
          skipAllowed={!!(chunk.data?.skip_allowed)}
        />
      );
      break;
    case "stats_context":
      content = (
        <>
          <ProgressStep label="Retrieved dataset statistics" isComplete={isComplete} />
          <StatsContextChunk
            content={chunk.content ?? ""}
            groups={chunk.data?.groups as string[]}
          />
        </>
      );
      break;
    default:
      content = null;
  }

  if (!content) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      {content}
    </motion.div>
  );
}

export const ChunkRenderer = React.memo(ChunkRendererInner);
