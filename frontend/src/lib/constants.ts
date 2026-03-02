export const SUGGESTED_QUESTIONS = [
  "Show the monthly transaction volume trend over time",
  "What are the top 5 merchant categories by total transaction value?",
  "Compare UPI vs credit card transaction patterns",
] as const;

// Regular API calls go through the CDN proxy (relative URL = first-party cookies).
export const API_BASE_URL = "";

// SSE streaming goes direct to Cloud Run (Bearer token auth, no buffering).
export const SSE_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

export const VALID_CHART_TYPES = new Set(["bar", "pie", "line", "grouped-bar", "table"]);
