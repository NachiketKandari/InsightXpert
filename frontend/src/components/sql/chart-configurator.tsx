"use client";

import { useState, useMemo } from "react";
import { BarChart3 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChartBlock } from "@/components/chunks/chart-block";
import { detectChartType, getChartConfig } from "@/lib/chart-detector";
import type { ChartType } from "@/lib/chart-detector";

interface ChartConfiguratorProps {
  columns: string[];
  rows: Record<string, unknown>[];
}

const CHART_TYPE_OPTIONS: { value: ChartType; label: string }[] = [
  { value: "bar", label: "Bar" },
  { value: "line", label: "Line" },
  { value: "pie", label: "Pie" },
  { value: "grouped-bar", label: "Grouped Bar" },
];

export function ChartConfigurator({ columns, rows }: ChartConfiguratorProps) {
  const { numericCols, categoryCols, categoryKey, valueKey, groupKey } =
    useMemo(() => getChartConfig(columns, rows), [columns, rows]);

  const detectedType = useMemo(
    () => detectChartType(columns, rows),
    [columns, rows],
  );

  const [chartType, setChartType] = useState<ChartType>(
    detectedType === "none" ? "bar" : detectedType,
  );
  const [xColumn, setXColumn] = useState(categoryKey);
  const [yColumn, setYColumn] = useState(valueKey);
  const [groupCol, setGroupCol] = useState(groupKey ?? categoryCols[1] ?? "");

  // Not chartable: need at least 2 columns and 2 rows with a numeric column
  if (columns.length < 2 || numericCols.length === 0 || rows.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
        <BarChart3 className="size-8 opacity-40" />
        <p className="text-sm">
          {columns.length < 2
            ? "Need at least 2 columns to visualize data."
            : numericCols.length === 0
              ? "No numeric columns found to chart."
              : "Need at least 2 rows to visualize data."}
        </p>
      </div>
    );
  }

  const availableGroupCols = categoryCols.filter((c) => c !== xColumn);

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      {/* Config toolbar */}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">Type</span>
          <Select
            value={chartType}
            onValueChange={(v) => setChartType(v as ChartType)}
          >
            <SelectTrigger className="h-7 w-[130px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CHART_TYPE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} className="text-xs">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">X</span>
          <Select value={xColumn} onValueChange={setXColumn}>
            <SelectTrigger className="h-7 w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {columns.map((col) => (
                <SelectItem key={col} value={col} className="text-xs">
                  {col}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">Y</span>
          <Select value={yColumn} onValueChange={setYColumn}>
            <SelectTrigger className="h-7 w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {numericCols.map((col) => (
                <SelectItem key={col} value={col} className="text-xs">
                  {col}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {chartType === "grouped-bar" && availableGroupCols.length > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground font-medium">Group</span>
            <Select value={groupCol} onValueChange={setGroupCol}>
              <SelectTrigger className="h-7 w-[140px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableGroupCols.map((col) => (
                  <SelectItem key={col} value={col} className="text-xs">
                    {col}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {/* Chart */}
      <ChartBlock
        columns={columns}
        rows={rows}
        suggestedChartType={chartType}
        xColumn={xColumn}
        yColumn={yColumn}
        groupColumn={chartType === "grouped-bar" ? groupCol : undefined}
        eager
      />
    </div>
  );
}
