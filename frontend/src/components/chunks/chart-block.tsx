"use client";

import { useState } from "react";
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
import { BarChart3, ChevronRight } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { detectChartType, getChartConfig, pivotData, hasStateCategories, abbreviateState } from "@/lib/chart-detector";
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

const VALID_CHART_TYPES = new Set(["bar", "pie", "line", "grouped-bar", "table"]);

interface ChartBlockProps {
  columns: string[];
  rows: Record<string, unknown>[];
  suggestedChartType?: string | null;
}

export function ChartBlock({ columns, rows, suggestedChartType }: ChartBlockProps) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(true);
  const chartType =
    suggestedChartType && VALID_CHART_TYPES.has(suggestedChartType)
      ? suggestedChartType
      : detectChartType(columns, rows);
  if (chartType === "none" || chartType === "table") return null;

  const { categoryKey, valueKey, groupKey } = getChartConfig(columns, rows);

  const data = rows.map((row) => ({
    ...row,
    [valueKey]: Number(row[valueKey]),
  }));

  const chartConfig: ChartConfig = {
    [valueKey]: {
      label: valueKey,
      color: "var(--color-chart-1)",
    },
  };

  const useStateCodes = hasStateCategories(data, categoryKey);
  const tickFormatter = useStateCodes ? (v: string) => abbreviateState(v) : undefined;

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
        <BarChart data={pivoted}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={categoryKey}
            tick={{ fontSize: 11 }}
            tickFormatter={groupedTickFormatter}
            tickLine={false}
            axisLine={false}
          />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
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
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={categoryKey}
            tick={{ fontSize: 11 }}
            tickFormatter={tickFormatter}
            tickLine={false}
            axisLine={false}
          />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
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
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, paddingTop: 4 }}
          />
        </PieChart>
      </ChartContainer>
    );
  } else {
    // line
    chartContent = (
      <ChartContainer config={chartConfig} className={`${isMobile ? "h-48" : "h-64"} w-full`}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" strokeOpacity={0.5} />
          <XAxis
            dataKey={categoryKey}
            tick={{ fontSize: 11 }}
            tickFormatter={tickFormatter}
            tickLine={false}
            axisLine={false}
          />
          <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
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
      <Card className="glass overflow-hidden">
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-2 w-full px-4 pt-3 pb-2 hover:bg-accent/30 transition-colors text-left">
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
        <CollapsibleContent>
          <CardContent className="pt-1 pb-2">
            {chartContent}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
