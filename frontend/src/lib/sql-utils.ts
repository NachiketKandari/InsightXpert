/**
 * Regex-based extraction of table names and column names from SQL queries.
 * These are lightweight heuristics — not a full SQL parser.
 */

/** Remove string literals, comments, and collapse whitespace. */
function normalizeSQL(sql: string): string {
  return sql
    .replace(/'[^']*'/g, "''")
    .replace(/--[^\n]*/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Extract table names referenced in FROM and JOIN clauses. */
export function extractTablesFromSQL(sql: string): string[] {
  const tables = new Set<string>();
  const normalized = normalizeSQL(sql);

  // FROM <table> patterns (handles aliases like "FROM transactions t")
  const fromPattern = /\bFROM\s+(\w+)/gi;
  let match: RegExpExecArray | null;
  while ((match = fromPattern.exec(normalized)) !== null) {
    tables.add(match[1].toLowerCase());
  }

  // JOIN <table> patterns
  const joinPattern = /\bJOIN\s+(\w+)/gi;
  while ((match = joinPattern.exec(normalized)) !== null) {
    tables.add(match[1].toLowerCase());
  }

  // Filter out SQL keywords that could be false positives
  const keywords = new Set(["select", "where", "group", "order", "having", "limit", "union", "values", "set"]);
  return Array.from(tables).filter((t) => !keywords.has(t));
}

/** Extract column names from the SELECT clause (before FROM). */
export function extractColumnsFromSQL(sql: string): string[] {
  const normalized = normalizeSQL(sql);

  // Extract the portion between SELECT and FROM
  const selectMatch = normalized.match(/\bSELECT\s+([\s\S]*?)\bFROM\b/i);
  if (!selectMatch) return [];

  const selectClause = selectMatch[1];
  if (selectClause.trim() === "*") return ["*"];

  // Split by commas, extract column name or alias
  return selectClause.split(",").map((part) => {
    const trimmed = part.trim();
    // Check for AS alias
    const asMatch = trimmed.match(/\bAS\s+(\w+)\s*$/i);
    if (asMatch) return asMatch[1];
    // Check for table.column or just column (last word)
    const words = trimmed.split(/\s+/);
    const last = words[words.length - 1];
    // Handle table.column
    const dotParts = last.split(".");
    return dotParts[dotParts.length - 1];
  }).filter(Boolean);
}
