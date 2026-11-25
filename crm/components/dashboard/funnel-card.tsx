"use client";

import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";

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
import type { FunnelStep, FunnelSummary } from "@/lib/analytics";

const chartConfig = {
  count: { label: "Count", color: "var(--chart-1)" },
} satisfies ChartConfig;

type FunnelCardProps = {
  funnel: FunnelSummary | null;
};

const EMPTY_STEPS: FunnelStep[] = [
  { key: "opportunities", label: "Opportunities", count: 0, conversion: null },
  { key: "evaluated", label: "Evaluated", count: 0, conversion: { value: null, n: 0 } },
  { key: "applied", label: "Applied", count: 0, conversion: { value: null, n: 0 } },
  { key: "interviewing", label: "Interviewing", count: 0, conversion: { value: null, n: 0 } },
  { key: "offers", label: "Offer", count: 0, conversion: { value: null, n: 0 } },
];

export function FunnelCard({ funnel }: FunnelCardProps) {
  const steps = funnel?.steps ?? EMPTY_STEPS;
  const data = steps.map((step) => ({
    stage: step.label,
    count: step.count,
    conversion:
      step.conversion?.value == null ? null : Math.round(step.conversion.value * 100),
  }));

  const colors = [
    "var(--chart-1)",
    "var(--chart-2)",
    "var(--chart-3)",
    "var(--chart-4)",
    "var(--chart-5)",
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Funnel</CardTitle>
        <CardDescription>Pipeline snapshot with step conversion rates</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-72 w-full">
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid horizontal={false} strokeDasharray="3 3" />
            <XAxis type="number" allowDecimals={false} />
            <YAxis type="category" dataKey="stage" width={96} tick={{ fontSize: 12 }} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="count" radius={4}>
              {data.map((entry, index) => (
                <Cell key={entry.stage} fill={colors[index % colors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
        <div className="mt-4 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
          {data.slice(1).map((step) => (
            <div key={step.stage} className="flex justify-between rounded-md border px-3 py-2">
              <span>{step.stage}</span>
              <span className="font-medium text-foreground">
                {step.conversion != null ? `${step.conversion}%` : "—"}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
