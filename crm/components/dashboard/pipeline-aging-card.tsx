"use client";

import Link from "next/link";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { stageLabel } from "@/components/dashboard/labels";
import type { PipelineAgingRow } from "@/lib/analytics";
import { formatDuration, formatNumber } from "@/lib/format";

/** Rows shown. The card lists the longest-waiting open applications first. */
export const AGING_ROW_LIMIT = 10;

type AgingBucket = {
  label: string;
  /** Sequential aging token: one hue, darker means older. */
  fill: string;
};

const RECENT: AgingBucket = { label: "Recent", fill: "bg-aging-ok" };
const AGING: AgingBucket = { label: "Aging", fill: "bg-aging-warn" };
const STALLED: AgingBucket = { label: "Stalled", fill: "bg-aging-critical" };

/** Matches the stalled threshold on the attention card: over 14 days is stalled. */
export function agingBucket(days: number): AgingBucket {
  if (days > 14) return STALLED;
  if (days > 7) return AGING;
  return RECENT;
}

const LEGEND: ReadonlyArray<{ bucket: AgingBucket; text: string }> = [
  { bucket: RECENT, text: "Up to 7 days" },
  { bucket: AGING, text: "8 to 14 days" },
  { bucket: STALLED, text: "Over 14 days" },
];

type PipelineAgingCardProps = {
  pipeline?: PipelineAgingRow[];
  status: CardStatus;
};

/**
 * Open applications as horizontal bars, longest-waiting first. Bars are scaled to the longest
 * row shown. Each row links to its application and carries a text label, so the bucket is
 * never read from colour alone.
 */
export function PipelineAgingCard({ pipeline, status }: PipelineAgingCardProps) {
  const rows = (pipeline ?? []).slice(0, AGING_ROW_LIMIT);
  const longest = Math.max(1, ...rows.map((row) => row.daysInStage));

  return (
    <DashboardCard
      title="Pipeline aging"
      description="Days each open application has been in its current stage, longest first."
      status={status}
      isEmpty={rows.length === 0}
      emptyTitle="No open applications"
      emptyDescription="Open applications appear here with the days they have spent in their stage."
      footer={
        (pipeline?.length ?? 0) > AGING_ROW_LIMIT ? (
          <p className="border-t pt-3 text-xs text-muted-foreground">
            Showing the {formatNumber(AGING_ROW_LIMIT)} longest of {formatNumber(pipeline?.length ?? 0)} open
            applications.
          </p>
        ) : null
      }
    >
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Aging legend">
        {LEGEND.map(({ bucket, text }) => (
          <li key={bucket.label} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={`size-2.5 rounded-sm ${bucket.fill}`} />
            <span>
              {bucket.label}, {text}
            </span>
          </li>
        ))}
      </ul>
      <ol className="space-y-1">
        {rows.map((row) => {
          const bucket = agingBucket(row.daysInStage);
          const width = (row.daysInStage / longest) * 100;
          return (
            <li key={row.applicationId}>
              <Link
                href={`/applications/${row.applicationId}`}
                className="block rounded-md px-2 py-2 hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring"
              >
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate font-medium">{row.title}</span>
                  <span className="shrink-0 text-xs font-medium tabular-nums">
                    {formatDuration(row.daysInStage)}
                  </span>
                </div>
                <div aria-hidden="true" className="mt-1 h-2 overflow-hidden rounded-sm bg-muted">
                  <div className={`h-full rounded-sm ${bucket.fill}`} style={{ width: `${width}%` }} />
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {row.company} · {stageLabel(row.stage)} · {bucket.label}
                </p>
              </Link>
            </li>
          );
        })}
      </ol>
    </DashboardCard>
  );
}
