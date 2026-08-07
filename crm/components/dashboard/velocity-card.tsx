"use client";

import { format } from "date-fns";
import { Bar, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { WeeklyActivity } from "@/lib/analytics";

const chartConfig = {
  applications: { label: "Applications", color: "var(--chart-1)" },
  interviews: { label: "Interviews", color: "var(--chart-2)" },
  rollingApplications: { label: "4-wk avg apps", color: "var(--chart-3)" },
} satisfies ChartConfig;

function rollingAverage(values: number[], index: number, window = 4) {
  const start = Math.max(0, index - window + 1);
  const slice = values.slice(start, index + 1);
  return Math.round((slice.reduce((a, b) => a + b, 0) / slice.length) * 10) / 10;
}

type VelocityCardProps = {
  weeklyActivity: WeeklyActivity[];
};

export function VelocityCard({ weeklyActivity }: VelocityCardProps) {
  const appValues = weeklyActivity.map((w) => w.applications ?? 0);
  const chartData = weeklyActivity.map((row, index) => ({
    week: format(new Date(row.week_start), "MMM d"),
    applications: row.applications ?? 0,
    interviews: row.interviews ?? 0,
    rollingApplications: rollingAverage(appValues, index),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Velocity</CardTitle>
        <CardDescription>Weekly applications and interviews</CardDescription>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <p className="text-sm text-muted-foreground">No activity in selected range</p>
        ) : (
          <ChartContainer config={chartConfig} className="h-72 w-full">
            <ComposedChart data={chartData} margin={{ left: 8, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="week" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} width={32} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="applications" fill="var(--color-applications)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="interviews" fill="var(--color-interviews)" radius={[4, 4, 0, 0]} />
              <Line
                type="monotone"
                dataKey="rollingApplications"
                stroke="var(--color-rollingApplications)"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
