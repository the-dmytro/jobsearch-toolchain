"use client";

import { format, parseISO } from "date-fns";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { TextAlternative } from "@/components/dashboard/text-alternative";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { WeeklyActivityPoint } from "@/lib/analytics";
import { formatNumber } from "@/lib/format";

const chartConfig = {
  applied: { label: "Applied", color: "var(--chart-1)" },
  responses: { label: "Responses", color: "var(--chart-2)" },
  interviews: { label: "Interviews", color: "var(--chart-3)" },
} satisfies ChartConfig;

type WeeklyRow = {
  weekStart: string;
  /** Short axis label, for example "3 Jun". */
  axis: string;
  /** Full week date for the tooltip and table, for example "3 Jun 2024". */
  weekDate: string;
  applied: number;
  responses: number;
  interviews: number;
};

function toRows(weekly: WeeklyActivityPoint[]): WeeklyRow[] {
  return weekly.map((week) => {
    const date = parseISO(week.weekStart);
    return {
      weekStart: week.weekStart,
      axis: format(date, "d MMM"),
      weekDate: format(date, "d MMM yyyy"),
      applied: week.applied,
      responses: week.responses,
      interviews: week.interviews,
    };
  });
}

type WeeklyActivityCardProps = {
  weeklyActivity?: WeeklyActivityPoint[];
  status: CardStatus;
};

export function WeeklyActivityCard({ weeklyActivity, status }: WeeklyActivityCardProps) {
  const rows = toRows(weeklyActivity ?? []);
  const total = rows.reduce((sum, row) => sum + row.applied + row.responses + row.interviews, 0);

  return (
    <DashboardCard
      title="Weekly activity"
      description="Count of applications, responses and interviews per week (weeks start on Monday)."
      status={status}
      isEmpty={rows.length === 0 || total === 0}
      emptyTitle="No activity in this range"
      emptyDescription="Weeks with applications, responses or interviews appear here."
    >
      <div aria-hidden="true">
        <ChartContainer config={chartConfig} className="h-64 w-full">
          <LineChart data={rows} margin={{ left: 4, right: 12, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="axis" tick={{ fontSize: 11 }} tickLine={false} minTickGap={16} />
            <YAxis allowDecimals={false} width={32} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(_value, payload) => {
                    const row = payload?.[0]?.payload as WeeklyRow | undefined;
                    return row ? `Week of ${row.weekDate}` : "";
                  }}
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Line type="linear" dataKey="applied" stroke="var(--color-applied)" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="linear" dataKey="responses" stroke="var(--color-responses)" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="linear" dataKey="interviews" stroke="var(--color-interviews)" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ChartContainer>
      </div>
      <TextAlternative<WeeklyRow>
        caption="Weekly activity: applications, responses and interviews per week"
        columns={[
          { key: "week", header: "Week starting", cell: (row) => row.weekDate },
          { key: "applied", header: "Applied", cell: (row) => formatNumber(row.applied) },
          { key: "responses", header: "Responses", cell: (row) => formatNumber(row.responses) },
          { key: "interviews", header: "Interviews", cell: (row) => formatNumber(row.interviews) },
        ]}
        rows={rows}
      />
    </DashboardCard>
  );
}
