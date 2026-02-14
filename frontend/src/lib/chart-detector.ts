export type ChartType = "bar" | "pie" | "line" | "none";

const TEMPORAL_PATTERNS =
  /\b(date|month|year|day|week|quarter|time|period|created_at|updated_at)\b/i;

export function detectChartType(
  columns: string[],
  rows: Record<string, unknown>[]
): ChartType {
  if (!rows.length || columns.length < 2) return "none";

  const numericCols = columns.filter((col) =>
    rows.every((row) => {
      const v = row[col];
      return v === null || v === undefined || typeof v === "number" || !isNaN(Number(v));
    })
  );

  const categoryCols = columns.filter((col) => !numericCols.includes(col));

  if (numericCols.length === 0) return "none";

  // Pie chart: 2-6 rows, one category + one numeric
  if (
    rows.length >= 2 &&
    rows.length <= 6 &&
    categoryCols.length === 1 &&
    numericCols.length === 1
  ) {
    return "pie";
  }

  // Line chart: temporal column detected
  const hasTemporal = columns.some((col) => TEMPORAL_PATTERNS.test(col));
  if (hasTemporal && rows.length >= 3) {
    return "line";
  }

  // Bar chart: category + numeric with more than 1 row
  if (categoryCols.length >= 1 && numericCols.length >= 1 && rows.length > 1) {
    return "bar";
  }

  return rows.length > 1 ? "bar" : "none";
}

export function getChartConfig(columns: string[], rows: Record<string, unknown>[]) {
  const numericCols = columns.filter((col) =>
    rows.every((row) => {
      const v = row[col];
      return v === null || v === undefined || typeof v === "number" || !isNaN(Number(v));
    })
  );
  const categoryCols = columns.filter((col) => !numericCols.includes(col));

  const categoryKey = categoryCols[0] || columns[0];
  const valueKey = numericCols[0] || columns[1];

  return { categoryKey, valueKey, numericCols, categoryCols };
}
