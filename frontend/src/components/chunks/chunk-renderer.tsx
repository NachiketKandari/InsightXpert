"use client";

import { motion } from "framer-motion";
import type { ChatChunk } from "@/types/chat";
import { parseToolResult } from "@/lib/chunk-parser";
import { StatusChunk } from "./status-chunk";
import { ToolCallChunk } from "./tool-call-chunk";
import { SqlChunk } from "./sql-chunk";
import { ToolResultChunk } from "./tool-result-chunk";
import { ChartBlock } from "./chart-block";
import { AnswerChunk } from "./answer-chunk";
import { ErrorChunk } from "./error-chunk";

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
      content = (
        <>
          <ToolResultChunk chunk={chunk} />
          {parsed && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut", delay: 0.1 }}
              className="mt-3"
            >
              <ChartBlock columns={parsed.columns} rows={parsed.rows} suggestedChartType={suggestedChartType} />
            </motion.div>
          )}
        </>
      );
      break;
    }
    case "answer":
      content = <AnswerChunk content={chunk.content ?? ""} />;
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
