import { TrendingDownIcon, TrendingUpIcon } from "lucide-react";

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { DashboardKpis, Rate, WeeklyActivityPoint } from "@/lib/analytics";
import { cn } from "@/lib/utils";

type KpiRowProps = {
  kpis: DashboardKpis;
  weeklyActivity: WeeklyActivityPoint[];
};

type KpiTile = {
  title: string;
  value: string | number;
  delta: number;
  hint?: string;
  sparkline?: number[];
};

function deltaLabel(current: number, previous: number) {
  return current - previous;
}

function percentOf(rate: Rate): number | null {
  return rate.value == null ? null : Math.round(rate.value * 100);
}

function rateValue(rate: Rate): string {
  const pct = percentOf(rate);
  return pct == null ? "—" : `${pct}%`;
}

function DeltaBadge({ delta }: { delta: number }) {
  if (delta === 0) {
    return <span className="text-xs text-muted-foreground">No change</span>;
  }

  const positive = delta > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-medium",
        positive ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
      )}
    >
      {positive ? <TrendingUpIcon className="size-3" /> : <TrendingDownIcon className="size-3" />}
      {positive ? "+" : ""}
      {delta}
    </span>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 100 - (value / max) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox="0 0 100 24" className="h-6 w-full text-chart-1" preserveAspectRatio="none">
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

export function KpiRow({ kpis, weeklyActivity }: KpiRowProps) {
  const appSpark = weeklyActivity.map((w) => w.applied);
  const oppSpark = weeklyActivity.map((w) => w.opportunities);
  const interviewSpark = weeklyActivity.map((w) => w.interviews);
  const responseDelta =
    percentOf(kpis.responseRate) != null && percentOf(kpis.responseRatePrev) != null
      ? deltaLabel(percentOf(kpis.responseRate) ?? 0, percentOf(kpis.responseRatePrev) ?? 0)
      : 0;
  const avgScoreDelta =
    kpis.avgScore != null && kpis.avgScorePrev != null
      ? Math.round((kpis.avgScore - kpis.avgScorePrev) * 10) / 10
      : 0;

  const tiles: KpiTile[] = [
    {
      title: "Open applications",
      value: kpis.openApplications,
      delta: deltaLabel(kpis.openApplications, kpis.openApplicationsPrev),
      hint: "Active pipeline",
    },
    {
      title: "Applied",
      value: kpis.appliedInRange,
      delta: deltaLabel(kpis.appliedInRange, kpis.appliedPrevPeriod),
      sparkline: appSpark,
    },
    {
      title: "Response rate",
      value: rateValue(kpis.responseRate),
      delta: responseDelta,
      hint: "Apps with reply in range",
    },
    {
      title: "Interviews",
      value: kpis.interviewsInRange,
      delta: deltaLabel(kpis.interviewsInRange, kpis.interviewsPrev),
      sparkline: interviewSpark,
    },
    {
      title: "New opportunities",
      value: kpis.newOpportunities,
      delta: deltaLabel(kpis.newOpportunities, kpis.newOpportunitiesPrev),
      sparkline: oppSpark,
    },
    {
      title: "Avg evaluation score",
      value: kpis.avgScore ?? "—",
      delta: avgScoreDelta,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {tiles.map((tile) => (
        <Card key={tile.title}>
          <CardHeader className="pb-2">
            <CardDescription>{tile.title}</CardDescription>
            <div className="flex items-end justify-between gap-2">
              <CardTitle className="text-3xl tabular-nums">{tile.value}</CardTitle>
              <DeltaBadge delta={tile.delta} />
            </div>
            {tile.hint ? (
              <p className="text-xs text-muted-foreground">{tile.hint}</p>
            ) : null}
            {tile.sparkline ? <Sparkline values={tile.sparkline} /> : null}
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}
