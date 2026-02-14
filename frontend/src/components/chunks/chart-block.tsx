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
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Card, CardContent } from "@/components/ui/card";
import { detectChartType, getChartConfig } from "@/lib/chart-detector";

const PIE_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
];

interface ChartBlockProps {
  columns: string[];
  rows: Record<string, unknown>[];
}

export function ChartBlock({ columns, rows }: ChartBlockProps) {
  const chartType = detectChartType(columns, rows);
  if (chartType === "none") return null;

  const { categoryKey, valueKey } = getChartConfig(columns, rows);

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
              <Bar
                dataKey={valueKey}
                fill="var(--color-chart-1)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    );
  }

  if (chartType === "pie") {
    return (
      <Card className="glass">
        <CardContent className="pt-4 pb-2">
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <PieChart>
              <ChartTooltip content={<ChartTooltipContent />} />
              <Pie
                data={data}
                dataKey={valueKey}
                nameKey={categoryKey}
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ name }) => String(name)}
              >
                {data.map((_, i) => (
                  <Cell
                    key={i}
                    fill={PIE_COLORS[i % PIE_COLORS.length]}
                  />
                ))}
              </Pie>
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
