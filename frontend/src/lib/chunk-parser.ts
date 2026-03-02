import type { ChatChunk } from "@/types/chat";

export function parseChunk(raw: string): ChatChunk | null {
  try {
    const parsed = JSON.parse(raw) as ChatChunk;
    if (!parsed.type) return null;
    return parsed;
  } catch {
    return null;
  }
}

interface ToolResultData {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
}

export function parseToolResult(chunk: ChatChunk): ToolResultData | null {
  if (chunk.type !== "tool_result" || !chunk.data) return null;

  const result = chunk.data.result;
  // Handle both string (normal) and pre-parsed object (edge case) formats
  if (!result) return null;

  try {
    const parsed = typeof result === "string" ? JSON.parse(result) : result;

    if (Array.isArray(parsed) && parsed.length > 0) {
      const columns = Object.keys(parsed[0]);
      return { columns, rows: parsed, rowCount: parsed.length };
    }

    if (typeof parsed === "object" && parsed !== null) {
      if (parsed.columns && parsed.data) {
        return {
          columns: parsed.columns,
          rows: parsed.data,
          rowCount: parsed.data.length,
        };
      }

      if (parsed.rows && Array.isArray(parsed.rows) && parsed.rows.length > 0) {
        const columns = Object.keys(parsed.rows[0]);
        return { columns, rows: parsed.rows, rowCount: parsed.row_count || parsed.rows.length };
      }

      // Nested array field (e.g. ranked_segments, anomalies, peaks, pairs)
      // Common in advanced analytics tool outputs
      const keys = Object.keys(parsed);
      const arrayField = keys.find(
        (k) =>
          Array.isArray(parsed[k]) &&
          parsed[k].length > 0 &&
          typeof parsed[k][0] === "object" &&
          parsed[k][0] !== null,
      );
      if (arrayField) {
        const rows = parsed[arrayField] as Record<string, unknown>[];
        const columns = Object.keys(rows[0]);
        return { columns, rows, rowCount: rows.length };
      }

      // Flat key-value object (e.g. descriptive stats, correlation results)
      // Convert to a 2-column table when there are enough fields
      if (keys.length >= 3 && keys.every((k) => !Array.isArray(parsed[k]) && typeof parsed[k] !== "object")) {
        const rows = keys.map((k) => ({ Metric: k, Value: parsed[k] }));
        return { columns: ["Metric", "Value"], rows, rowCount: rows.length };
      }
    }
  } catch {
    // result might not be JSON (e.g., plain text error)
  }

  return null;
}
