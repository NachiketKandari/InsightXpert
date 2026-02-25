"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { CheckCircle, Loader2 } from "lucide-react";
import type { ChatChunk } from "@/types/chat";
import { parseToolResult } from "@/lib/chunk-parser";
import { detectChartType } from "@/lib/chart-detector";
import { VALID_CHART_TYPES } from "@/lib/constants";
import { StatusChunk } from "./status-chunk";
import { ToolCallChunk } from "./tool-call-chunk";
import { SqlChunk } from "./sql-chunk";
import { ToolResultChunk } from "./tool-result-chunk";
import { ChartBlock } from "./chart-block";
import { AnswerChunk } from "./answer-chunk";
import { ErrorChunk } from "./error-chunk";

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
}

export function ChunkRenderer({ chunk, isComplete }: ChunkRendererProps) {
  let content: React.ReactNode;

  switch (chunk.type) {
    case "status":
      content = <StatusChunk content={chunk.content ?? ""} isComplete={isComplete} />;
      break;
    case "tool_call":
      content = <ToolCallChunk content={chunk.content ?? ""} isComplete={isComplete} />;
      break;
    case "sql":
      content = chunk.sql ? <SqlChunk sql={chunk.sql} /> : null;
      break;
    case "tool_result": {
      const parsed = parseToolResult(chunk);
      const suggestedChartType = (chunk.data?.visualization as string) ?? null;

      let willShowChart = false;
      if (parsed) {
        const chartType =
          suggestedChartType && VALID_CHART_TYPES.has(suggestedChartType)
            ? suggestedChartType
            : detectChartType(parsed.columns, parsed.rows);
        willShowChart = chartType !== "none" && chartType !== "table";
      }

      content = (
        <>
          <ToolResultChunk chunk={chunk} />
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
                <ChartBlock columns={parsed.columns} rows={parsed.rows} suggestedChartType={suggestedChartType} />
              </motion.div>
            </>
          )}
        </>
      );
      break;
    }
    case "answer":
      content = (
        <>
          <ProgressStep label="Generating answer" isComplete={isComplete} />
          <AnswerChunk content={chunk.content ?? ""} />
        </>
      );
      break;
    case "error":
      content = <ErrorChunk content={chunk.content ?? "An error occurred"} />;
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
