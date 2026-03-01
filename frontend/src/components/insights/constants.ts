/** Map enrichment categories to tailwind badge colors (amber/gold theme). */
export const CATEGORY_COLOR: Record<string, string> = {
  trend_analysis: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  anomaly_detection: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  comparative: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  predictive: "bg-lime-100 text-lime-800 dark:bg-lime-900/40 dark:text-lime-300",
  segmentation: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  correlation: "bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300",
  root_cause: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  statistical: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
};

export const DEFAULT_CATEGORY_COLOR =
  "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400";
