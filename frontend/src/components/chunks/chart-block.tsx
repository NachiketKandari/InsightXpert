"use client";

import React, { useState, useMemo, useRef, useEffect } from "react";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
  Legend,
} from "recharts";
import { BarChart3, ChevronRight, Download, Loader2 } from "lucide-react";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn, downloadCsv } from "@/lib/utils";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { detectChartType, getChartConfig, pivotData, hasStateCategories, abbreviateState } from "@/lib/chart-detector";
import { VALID_CHART_TYPES } from "@/lib/constants";
import { useIsMobile } from "@/hooks/use-media-query";

const CHART_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
  "var(--color-chart-6)",
  "var(--color-chart-7)",
  "var(--color-chart-8)",
];

interface ChartBlockProps {
  columns: string[];
  rows: Record<string, unknown>[];
  suggestedChartType?: string | null;
  /** Explicit x-axis column from the LLM. Falls back to auto-detect if not provided. */
  xColumn?: string;
  /** Explicit y-axis column from the LLM. Falls back to auto-detect if not provided. */
  yColumn?: string;
  /** Skip lazy loading (render immediately) for currently-streaming messages. */
  eager?: boolean;
}

function ChartBlockInner({ columns, rows, suggestedChartType, xColumn, yColumn }: ChartBlockProps) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(true);

  const chartType = useMemo(
    () =>
      suggestedChartType && VALID_CHART_TYPES.has(suggestedChartType)
        ? suggestedChartType
        : detectChartType(columns, rows),
    [columns, rows, suggestedChartType],
  );

  const { categoryKey, valueKey, groupKey } = useMemo(() => {
    const auto = getChartConfig(columns, rows);
    return {
      categoryKey: (xColumn && columns.includes(xColumn)) ? xColumn : auto.categoryKey,
      valueKey: (yColumn && columns.includes(yColumn)) ? yColumn : auto.valueKey,
      groupKey: auto.groupKey,
    };
  }, [columns, rows, xColumn, yColumn]);

  const data = useMemo(
    () => rows.map((row) => ({ ...row, [valueKey]: Number(row[valueKey]) })),
    [rows, valueKey],
  );

  const chartConfig: ChartConfig = useMemo(
    () => ({
      [valueKey]: { label: valueKey, color: "var(--color-chart-1)" },
    }),
    [valueKey],
  );

  const useStateCodes = useMemo(() => hasStateCategories(data, categoryKey), [data, categoryKey]);
  const tickFormatter = useMemo(
    () => (useStateCodes ? (v: string) => abbreviateState(v) : undefined),
    [useStateCodes],
  );

  /** Format a column key into a readable axis label (e.g. "total_amount" → "Total Amount"). */
  const formatLabel = (key: string) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const xLabel = formatLabel(categoryKey);
  const yLabel = formatLabel(valueKey);

  // Place labels in dedicated margin space so they never overlap tick text.
  // On mobile, skip labels entirely — charts are too compact.
  const labelStyle = { fontSize: 10, fill: "var(--color-muted-foreground)" };
  const xAxisLabel = isMobile
    ? undefined
    : { value: xLabel, position: "insideBottom" as const, offset: -18, style: labelStyle };
  const yAxisLabel = isMobile
    ? undefined
    : { value: yLabel, angle: -90, position: "insideLeft" as const, dx: -25, style: { ...labelStyle, textAnchor: "middle" as const } };

  const chartMargin = isMobile
    ? undefined
    : { top: 5, right: 5, bottom: 25, left: 30 };

  if (chartType === "none" || chartType === "table") return null;

  let chartContent: React.ReactNode;

  if (chartType === "grouped-bar" && groupKey) {
    const { pivoted, groupValues } = pivotData(rows, categoryKey, groupKey, valueKey);

    const groupedConfig: ChartConfig = {};
    groupValues.forEach((gv, i) => {
      groupedConfig[gv] = {
        label: gv,
        color: CHART_COLORS[i % CHART_COLORS.length],
      };
    });

    const useStateCodesGrouped = hasStateCategories(pivoted, categoryKey);
    const groupedTickFormatter = useStateCodesGrouped ? (v: string) => abbreviateState(v) : undefined;

    chartContent = (
      <ChartContainer config={groupedConfig} className={`${isMobile ? "h-56" : "h-72"} w-full`}>
        <BarChart data={pivoted} margin={isMobile ? undefined : { top: 5, right: 5, bottom: 25, left: 30 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={categoryKey}
            tick={{ fontSize: 11 }}
            tickFormatter={groupedTickFormatter}
            tickLine={false}
            axisLine={false}
            label={xAxisLabel}
          />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} label={yAxisLabel} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Legend
            verticalAlign="top"
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, paddingBottom: 8 }}
          />
          {groupValues.map((gv, i) => (
            <Bar
              key={gv}
              dataKey={gv}
              fill={CHART_COLORS[i % CHART_COLORS.length]}
              radius={[4, 4, 0, 0]}
            />
          ))}
        </BarChart>
      </ChartContainer>
    );
  } else if (chartType === "bar") {
    chartContent = (
      <ChartContainer config={chartConfig} className={`${isMobile ? "h-48" : "h-64"} w-full`}>
        <BarChart data={data} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={categoryKey}
            tick={{ fontSize: 11 }}
            tickFormatter={tickFormatter}
            tickLine={false}
            axisLine={false}
            label={xAxisLabel}
          />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} label={yAxisLabel} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Bar dataKey={valueKey} radius={[4, 4, 0, 0]}>
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
              />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>
    );
  } else if (chartType === "pie") {
    const total = data.reduce((sum, row) => sum + Number(row[valueKey]), 0);

    chartContent = (
      <ChartContainer config={chartConfig} className={`${isMobile ? "h-60" : "h-72"} w-full`}>
        <PieChart>
          <ChartTooltip content={<ChartTooltipContent />} />
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={categoryKey}
            cx="50%"
            cy="45%"
            outerRadius={isMobile ? 65 : 85}
            label={isMobile ? false : ({ name, value }) => {
              const pct = ((Number(value) / total) * 100).toFixed(1);
              const label = useStateCodes ? abbreviateState(String(name)) : name;
              return `${label} (${pct}%)`;
            }}
            labelLine={isMobile ? false : { strokeWidth: 1 }}
          >
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
              />
            ))}
          </Pie>
          <Legend
            verticalAlign="top"
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, paddingBottom: 8 }}
          />
        </PieChart>
      </ChartContainer>
    );
  } else {
    // line
    chartContent = (
      <ChartContainer config={chartConfig} className={`${isMobile ? "h-48" : "h-64"} w-full`}>
        <LineChart data={data} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={categoryKey}
            tick={{ fontSize: 11 }}
            tickFormatter={tickFormatter}
            tickLine={false}
            axisLine={false}
            label={xAxisLabel}
          />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} label={yAxisLabel} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Line
            type="monotone"
            dataKey={valueKey}
            stroke="var(--color-chart-1)"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ChartContainer>
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="glass overflow-hidden py-0 gap-0">
        <div className="flex items-center justify-between pr-2">
          <CollapsibleTrigger asChild>
            <button className="flex items-center gap-2 flex-1 px-4 pt-3 pb-2 hover:bg-accent/30 transition-colors text-left">
              <ChevronRight
                className={cn(
                  "size-4 shrink-0 text-muted-foreground transition-transform duration-200",
                  open && "rotate-90"
                )}
              />
              <BarChart3 className="size-4 shrink-0 text-muted-foreground" />
              <Badge variant="secondary" className="text-xs">
                Visualization
              </Badge>
            </button>
          </CollapsibleTrigger>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  downloadCsv(columns, rows, "insightxpert-chart-data.csv");
                }}
                className="flex items-center justify-center size-7 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors shrink-0"
                aria-label="Download CSV"
              >
                <Download className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Download CSV</TooltipContent>
          </Tooltip>
        </div>
        <CollapsibleContent>
          <CardContent className="px-2 pt-1 pb-2">
            {chartContent}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

const MemoizedChartBlock = React.memo(ChartBlockInner);

/**
 * Lazy-loading wrapper: defers mounting until the element is near the viewport.
 * For streaming messages (`eager`), renders immediately without the observer.
 */
export function ChartBlock({ eager, ...props }: ChartBlockProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(!!eager);

  useEffect(() => {
    if (eager || visible) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [eager, visible]);

  if (visible) return <MemoizedChartBlock {...props} />;

  return (
    <div ref={ref} className="flex items-center gap-2 text-muted-foreground text-sm py-6 justify-center">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>Chart loading...</span>
    </div>
  );
}
