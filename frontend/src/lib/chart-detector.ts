export type ChartType = "bar" | "pie" | "line" | "grouped-bar" | "none";

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

  // Grouped bar chart: 2 category columns + numeric (e.g. age_group × transaction_type × count)
  if (categoryCols.length === 2 && numericCols.length >= 1 && rows.length > 2) {
    return "grouped-bar";
  }

  // Pie chart: up to 10 rows, one category + one numeric
  if (
    rows.length >= 2 &&
    rows.length <= 10 &&
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

export interface ChartConfigResult {
  categoryKey: string;
  valueKey: string;
  numericCols: string[];
  categoryCols: string[];
  groupKey?: string;
}

export function getChartConfig(
  columns: string[],
  rows: Record<string, unknown>[]
): ChartConfigResult {
  const numericCols = columns.filter((col) =>
    rows.every((row) => {
      const v = row[col];
      return v === null || v === undefined || typeof v === "number" || !isNaN(Number(v));
    })
  );
  const categoryCols = columns.filter((col) => !numericCols.includes(col));

  const categoryKey = categoryCols[0] || columns[0];
  const valueKey = numericCols[0] || columns[1];
  const groupKey = categoryCols.length >= 2 ? categoryCols[1] : undefined;

  return { categoryKey, valueKey, numericCols, categoryCols, groupKey };
}

/** Pivot rows for grouped bar charts — groups by categoryKey with a column per groupKey value. */
export function pivotData(
  rows: Record<string, unknown>[],
  categoryKey: string,
  groupKey: string,
  valueKey: string
): { pivoted: Record<string, unknown>[]; groupValues: string[] } {
  const groupValues = [...new Set(rows.map((r) => String(r[groupKey])))];
  const grouped = new Map<string, Record<string, unknown>>();

  for (const row of rows) {
    const cat = String(row[categoryKey]);
    if (!grouped.has(cat)) {
      grouped.set(cat, { [categoryKey]: cat });
    }
    const entry = grouped.get(cat)!;
    entry[String(row[groupKey])] = Number(row[valueKey]);
  }

  return { pivoted: [...grouped.values()], groupValues };
}
