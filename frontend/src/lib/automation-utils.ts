export type ResultShape = "scalar" | "single_row" | "tabular";

export function detectResultShape(columns: string[], rows: Record<string, unknown>[]): ResultShape {
  if (rows.length === 0) return "tabular";
  if (rows.length === 1 && columns.length === 1) return "scalar";
  if (rows.length === 1) return "single_row";
  return "tabular";
}

export function cronToHumanReadable(cron: string): string {
  const parts = cron.split(" ");
  if (parts.length !== 5) return cron;
  const [min, hour, dom, mon, dow] = parts;

  if (min === "0" && hour === "*" && dom === "*" && mon === "*" && dow === "*") return "Every hour";
  if (min === "0" && dom === "*" && mon === "*" && dow === "*") return `Daily at ${hour}:00`;
  if (min === "0" && dom === "*" && mon === "*" && dow === "1") return `Weekly on Monday at ${hour}:00`;
  if (min === "0" && dom === "1" && mon === "*" && dow === "*") return `Monthly on the 1st at ${hour}:00`;

  return `Cron: ${cron}`;
}

export const SCHEDULE_PRESETS = {
  hourly: "0 * * * *",
  daily: "0 9 * * *",
  weekly: "0 9 * * 1",
  monthly: "0 9 1 * *",
} as const;

export function presetToCron(preset: string): string | null {
  return SCHEDULE_PRESETS[preset as keyof typeof SCHEDULE_PRESETS] ?? null;
}

export const OPERATOR_LABELS: Record<string, string> = {
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  eq: "=",
  ne: "!=",
};
