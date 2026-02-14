"use client";

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
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Card, CardContent } from "@/components/ui/card";
import { detectChartType, getChartConfig, pivotData } from "@/lib/chart-detector";

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
}

export function ChartBlock({ columns, rows }: ChartBlockProps) {
  const chartType = detectChartType(columns, rows);
  if (chartType === "none") return null;

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

  if (chartType === "grouped-bar" && groupKey) {
    const { pivoted, groupValues } = pivotData(rows, categoryKey, groupKey, valueKey);

    const groupedConfig: ChartConfig = {};
    groupValues.forEach((gv, i) => {
      groupedConfig[gv] = {
        label: gv,
        color: CHART_COLORS[i % CHART_COLORS.length],
      };
    });

    return (
      <Card className="glass">
        <CardContent className="pt-4 pb-2">
          <ChartContainer config={groupedConfig} className="h-72 w-full">
            <BarChart data={pivoted}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey={categoryKey}
                tick={{ fontSize: 11 }}
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
        </CardContent>
      </Card>
    );
  }

  if (chartType === "bar") {
    return (
      <Card className="glass">
        <CardContent className="pt-4 pb-2">
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey={categoryKey}
                tick={{ fontSize: 11 }}
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
        </CardContent>
      </Card>
    );
  }

  if (chartType === "pie") {
    const total = data.reduce((sum, row) => sum + Number(row[valueKey]), 0);

    return (
      <Card className="glass">
        <CardContent className="pt-4 pb-2">
          <ChartContainer config={chartConfig} className="h-72 w-full">
            <PieChart>
              <ChartTooltip content={<ChartTooltipContent />} />
              <Pie
                data={data}
                dataKey={valueKey}
                nameKey={categoryKey}
                cx="50%"
                cy="45%"
                outerRadius={85}
                label={({ name, value }) => {
                  const pct = ((Number(value) / total) * 100).toFixed(1);
                  return `${name} (${pct}%)`;
                }}
                labelLine={{ strokeWidth: 1 }}
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
        </CardContent>
      </Card>
    );
  }

  // line
  return (
    <Card className="glass">
      <CardContent className="pt-4 pb-2">
        <ChartContainer config={chartConfig} className="h-64 w-full">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey={categoryKey}
              tick={{ fontSize: 11 }}
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
      </CardContent>
    </Card>
  );
}
