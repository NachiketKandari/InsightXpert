export const SUGGESTED_QUESTIONS = [
  "Show the monthly transaction volume trend over time",
  "What are the top 5 merchant categories by total transaction value?",
  "Compare UPI vs credit card transaction patterns",
] as const;

export const CHUNK_TYPES = {
  STATUS: "status",
  TOOL_CALL: "tool_call",
  SQL: "sql",
  TOOL_RESULT: "tool_result",
  ANSWER: "answer",
  ERROR: "error",
} as const;

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";
