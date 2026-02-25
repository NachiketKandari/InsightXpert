export type ChartType = "bar" | "pie" | "line" | "grouped-bar" | "none";

/** RTO codes for all 36 Indian states and union territories */
const STATE_CODES: Record<string, string> = {
  "andhra pradesh": "AP",
  "arunachal pradesh": "AR",
  "assam": "AS",
  "bihar": "BR",
  "chhattisgarh": "CG",
  "goa": "GA",
  "gujarat": "GJ",
  "haryana": "HR",
  "himachal pradesh": "HP",
  "jharkhand": "JH",
  "karnataka": "KA",
  "kerala": "KL",
  "madhya pradesh": "MP",
  "maharashtra": "MH",
  "manipur": "MN",
  "meghalaya": "ML",
  "mizoram": "MZ",
  "nagaland": "NL",
  "odisha": "OD",
  "punjab": "PB",
  "rajasthan": "RJ",
  "sikkim": "SK",
  "tamil nadu": "TN",
  "telangana": "TS",
  "tripura": "TR",
  "uttar pradesh": "UP",
  "uttarakhand": "UK",
  "west bengal": "WB",
  "andaman and nicobar islands": "AN",
  "chandigarh": "CH",
  "dadra and nagar haveli and daman and diu": "DD",
  "delhi": "DL",
  "jammu and kashmir": "JK",
  "ladakh": "LA",
  "lakshadweep": "LD",
  "puducherry": "PY",
};

/** Return RTO code for a state name, or null if not a state */
export function getStateCode(name: string): string | null {
  return STATE_CODES[name.toLowerCase().trim()] ?? null;
}

/** Abbreviate a value to its RTO code if it's a state name, otherwise return as-is */
export function abbreviateState(name: string): string {
  return getStateCode(name) ?? name;
}

/** Check if the majority of category values are Indian state names */
export function hasStateCategories(
  data: Record<string, unknown>[],
  categoryKey: string,
): boolean {
  if (data.length === 0) return false;
  const matchCount = data.filter(
    (row) => getStateCode(String(row[categoryKey])) !== null,
  ).length;
  return matchCount > data.length / 2;
}

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
  const valueKey = numericCols.find((col) => col !== categoryKey) || columns[1];
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
