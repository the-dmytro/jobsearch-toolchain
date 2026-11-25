"use client";

import { MinusIcon, TrendingDownIcon, TrendingUpIcon, type LucideIcon } from "lucide-react";

import { CardSkeleton } from "@/components/crm/card-skeleton";
import { ErrorState } from "@/components/crm/error-state";
import type { CardStatus } from "@/components/dashboard/dashboard-card";
import { signedChange } from "@/components/dashboard/labels";
import { Sparkline } from "@/components/dashboard/sparkline";
import { Card, CardContent } from "@/components/ui/card";
import type { DashboardKpis, Rate, WeeklyActivityPoint } from "@/lib/analytics";
import { formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Rates with fewer applications than this are not shown as a percentage. */
export const MIN_RATE_SAMPLE = 5;

/**
 * Which direction is good for each metric. "neutral" means a change is information, not a
 * verdict: fewer applications sent, or a smaller open pipeline, is not automatically bad.
 */
type GoodWhen = "up" | "neutral";

type Delta =
  | { kind: "change"; direction: "up" | "down" | "flat"; text: string; tone: "good" | "bad" | "neutral" }
  | { kind: "message"; text: string };

type KpiTile = {
  id: string;
  label: string;
  value: string;
  valueIsText?: boolean;
  sub?: string;
  delta: Delta;
  spark?: { values: number[]; label: string };
};

export type KpiRowProps = {
  kpis?: DashboardKpis;
  weeklyActivity?: WeeklyActivityPoint[];
  status: CardStatus;
  /** False for "all time", which has no earlier period to compare with. */
  showDeltas: boolean;
};

const DIRECTION_ICON: Record<"up" | "down" | "flat", LucideIcon> = {
  up: TrendingUpIcon,
  down: TrendingDownIcon,
  flat: MinusIcon,
};

const TONE_CLASS: Record<"good" | "bad" | "neutral", string> = {
  good: "text-success",
  bad: "text-danger",
  neutral: "text-muted-foreground",
};

const NO_PREVIOUS = "No earlier period to compare";

function hasSample(rate: Rate): boolean {
  return rate.value != null && rate.n >= MIN_RATE_SAMPLE;
}

function changeDelta(
  diff: number,
  goodWhen: GoodWhen,
  format: (value: number) => string,
  suffix: string
): Delta {
  if (diff === 0) {
    return { kind: "change", direction: "flat", text: `No change ${suffix}`, tone: "neutral" };
  }
  const direction = diff > 0 ? "up" : "down";
  const tone = goodWhen === "neutral" ? "neutral" : direction === goodWhen ? "good" : "bad";
  return { kind: "change", direction, text: `${format(diff)} ${suffix}`, tone };
}

function countDelta(current: number, previous: number, goodWhen: GoodWhen, showDeltas: boolean): Delta {
  if (!showDeltas) return { kind: "message", text: NO_PREVIOUS };
  return changeDelta(current - previous, goodWhen, (diff) => signedChange(diff), "vs previous period");
}

function rateDelta(current: Rate, previous: Rate, showDeltas: boolean): Delta {
  if (!showDeltas) return { kind: "message", text: NO_PREVIOUS };
  if (!hasSample(current) || !hasSample(previous)) {
    return { kind: "message", text: "Not enough data to compare" };
  }
  const diff = Math.round(((current.value ?? 0) - (previous.value ?? 0)) * 100);
  return changeDelta(diff, "up", (value) => `${signedChange(value)} pts`, "vs previous period");
}

function scoreDelta(current: number | null, previous: number | null, showDeltas: boolean): Delta {
  if (!showDeltas) return { kind: "message", text: NO_PREVIOUS };
  if (current == null || previous == null) return { kind: "message", text: "No scores to compare" };
  const diff = Math.round((current - previous) * 10) / 10;
  return changeDelta(diff, "up", (value) => signedChange(value, 1), "vs previous period");
}

function rateTile(id: string, label: string, rate: Rate, previous: Rate, showDeltas: boolean): KpiTile {
  if (!hasSample(rate)) {
    return {
      id,
      label,
      value: "Not enough data",
      valueIsText: true,
      sub: rate.n === 0 ? "No applications in range" : `Only ${formatNumber(rate.n)} so far`,
      delta: showDeltas
        ? { kind: "message", text: "Not enough data to compare" }
        : { kind: "message", text: NO_PREVIOUS },
    };
  }
  return {
    id,
    label,
    value: formatPercent(rate.value),
    sub: `· ${formatNumber(rate.n)} apps`,
    delta: rateDelta(rate, previous, showDeltas),
  };
}

function buildTiles(kpis: DashboardKpis, weekly: WeeklyActivityPoint[], showDeltas: boolean): KpiTile[] {
  return [
    {
      id: "applied",
      label: "Applications sent",
      value: formatNumber(kpis.appliedInRange),
      sub: "Applied in range",
      // Volume is an input, not an outcome, so a change is shown without a good or bad colour.
      delta: countDelta(kpis.appliedInRange, kpis.appliedPrevPeriod, "neutral", showDeltas),
      spark: { values: weekly.map((week) => week.applied), label: "Applications per week" },
    },
    rateTile("response", "Response rate", kpis.responseRate, kpis.responseRatePrev, showDeltas),
    {
      id: "interviews",
      label: "Interviews",
      value: formatNumber(kpis.interviewsInRange),
      sub: "Held so far in range",
      delta: countDelta(kpis.interviewsInRange, kpis.interviewsPrev, "up", showDeltas),
      spark: { values: weekly.map((week) => week.interviews), label: "Interviews per week" },
    },
    {
      id: "offers",
      label: "Offers",
      value: formatNumber(kpis.offersInRange),
      sub: "Applications that reached an offer",
      delta: countDelta(kpis.offersInRange, kpis.offersPrev, "up", showDeltas),
    },
    {
      id: "open",
      label: "Open pipeline",
      value: formatNumber(kpis.openApplications),
      sub: "Still awaiting a decision",
      delta: countDelta(kpis.openApplications, kpis.openApplicationsPrev, "neutral", showDeltas),
    },
    {
      id: "score",
      label: "Average score",
      value: kpis.avgScore == null ? "—" : kpis.avgScore.toFixed(1),
      sub: kpis.avgScore == null ? "No evaluations in range" : "Match score, 0 to 10",
      delta: scoreDelta(kpis.avgScore, kpis.avgScorePrev, showDeltas),
    },
  ];
}

function DeltaLine({ delta }: { delta: Delta }) {
  if (delta.kind === "message") {
    return <p className="text-xs text-muted-foreground">{delta.text}</p>;
  }
  const Icon = DIRECTION_ICON[delta.direction];
  return (
    <p className={cn("inline-flex items-center gap-1 text-xs font-medium", TONE_CLASS[delta.tone])}>
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>{delta.text}</span>
    </p>
  );
}

export function KpiRow({ kpis, weeklyActivity, status, showDeltas }: KpiRowProps) {
  if (status.loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <CardSkeleton key={index} lines={2} label="Loading key figures" />
        ))}
      </div>
    );
  }

  if (status.error || !kpis) {
    return (
      <ErrorState title="Couldn't load key figures" error={status.error} onRetry={status.onRetry} />
    );
  }

  const tiles = buildTiles(kpis, weeklyActivity ?? [], showDeltas);

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {tiles.map((tile) => (
        <article key={tile.id} aria-labelledby={`kpi-${tile.id}`} className="min-w-0">
          <Card size="sm" className="h-full">
            <CardContent className="flex h-full flex-col gap-2">
              <p id={`kpi-${tile.id}`} className="text-sm font-medium text-muted-foreground">
                {tile.label}
              </p>
              <p
                className={cn(
                  "flex flex-wrap items-baseline gap-x-2 font-semibold tracking-tight tabular-nums",
                  tile.valueIsText ? "text-base text-muted-foreground" : "text-3xl text-foreground"
                )}
              >
                <span>{tile.value}</span>
                {tile.sub ? (
                  <span className="text-sm font-normal text-muted-foreground">{tile.sub}</span>
                ) : null}
              </p>
              <DeltaLine delta={tile.delta} />
              {tile.spark ? <Sparkline values={tile.spark.values} label={tile.spark.label} /> : null}
            </CardContent>
          </Card>
        </article>
      ))}
    </div>
  );
}
