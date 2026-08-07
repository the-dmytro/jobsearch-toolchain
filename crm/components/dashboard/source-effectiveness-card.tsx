"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { SourceEffectiveness } from "@/lib/analytics";

const chartConfig = {
  app_to_interview_pct: {
    label: "App → interview %",
    color: "var(--chart-4)",
  },
} satisfies ChartConfig;

type SourceEffectivenessCardProps = {
  sources: SourceEffectiveness[];
};

export function SourceEffectivenessCard({ sources }: SourceEffectivenessCardProps) {
  const chartData = sources
    .filter((s) => (s.applications ?? 0) > 0)
    .slice(0, 8)
    .map((s) => ({
      source: s.provider_slug ?? s.provider_name ?? "unknown",
      app_to_interview_pct: s.app_to_interview_pct ?? 0,
      applications: s.applications ?? 0,
      interviews: s.interviews ?? 0,
    }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Source effectiveness</CardTitle>
        <CardDescription>Application-to-interview conversion by provider</CardDescription>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <p className="text-sm text-muted-foreground">No application data yet</p>
        ) : (
          <ChartContainer config={chartConfig} className="h-72 w-full">
            <BarChart data={chartData} margin={{ left: 8, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="source" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} width={32} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    formatter={(value, _name, item) => {
                      const payload = item.payload as {
                        applications?: number;
                        interviews?: number;
                      };
                      return (
                        <span>
                          {value}% ({payload.applications ?? 0} apps,{" "}
                          {payload.interviews ?? 0} interviews)
                        </span>
                      );
                    }}
                  />
                }
              />
              <Bar
                dataKey="app_to_interview_pct"
                fill="var(--color-app_to_interview_pct)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
