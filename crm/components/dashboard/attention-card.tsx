"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { stageLabel } from "@/components/dashboard/labels";
import { Badge } from "@/components/ui/badge";
import type { AttentionBundle } from "@/lib/analytics";
import { formatDate, formatDuration, formatNumber, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Rows shown per list. The full set is one click away on its own page. */
export const ATTENTION_ROW_LIMIT = 5;

type AttentionCardProps = {
  attention?: AttentionBundle;
  status: CardStatus;
};

function AttentionList({
  headingId,
  title,
  count,
  emptyText,
  viewAllHref,
  viewAllLabel,
  children,
}: {
  headingId: string;
  title: string;
  count: number;
  emptyText: string;
  viewAllHref: string;
  viewAllLabel: string;
  children: ReactNode[];
}) {
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 id={headingId} className="text-sm font-medium">
          {title}
        </h3>
        <Badge variant="secondary" className="tabular-nums">
          {formatNumber(count)}
        </Badge>
      </div>
      {count === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <ul className="flex flex-col gap-2">{children}</ul>
      )}
      <Link
        href={viewAllHref}
        className="mt-auto self-start text-sm font-medium text-primary underline-offset-4 hover:underline"
      >
        View all
        <span className="sr-only"> {viewAllLabel}</span>
      </Link>
    </section>
  );
}

const ROW_CLASS =
  "flex min-w-0 flex-col gap-1 rounded-md border px-3 py-2 text-sm hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring";

/** Stalled-days chip: aging token plus a text label, so the state never relies on colour alone. */
function StalledChip({ days }: { days: number }) {
  return (
    <span className="inline-flex w-fit items-center rounded-md bg-aging-critical px-2 py-0.5 text-xs font-medium tabular-nums text-background">
      Stalled · {formatDuration(days)}
    </span>
  );
}

/**
 * Items that need a look now: interviews in the next seven days, open applications stuck in
 * their stage, and automation failures in the last seven days. Each list links to its page.
 */
export function AttentionCard({ attention, status }: AttentionCardProps) {
  const upcoming = attention?.upcomingInterviews ?? [];
  const stalled = attention?.stalled ?? [];
  const runErrors = attention?.runErrors ?? [];

  return (
    <DashboardCard
      title="Needs attention"
      description="Upcoming interviews, applications stuck in one stage, and automation failures."
      status={status}
      isEmpty={false}
      className="lg:col-span-full"
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <AttentionList
          headingId="attention-upcoming"
          title="Upcoming interviews (7 days)"
          count={upcoming.length}
          emptyText="No interviews in the next 7 days."
          viewAllHref="/interviews"
          viewAllLabel="upcoming interviews"
        >
          {upcoming.slice(0, ATTENTION_ROW_LIMIT).map((row) => (
            <li key={row.interviewId}>
              <Link href={`/interviews/${row.interviewId}`} className={ROW_CLASS}>
                <span className="font-medium">{formatRelative(row.scheduledAt)}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatDate(row.scheduledAt, { withTime: true })}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {row.company} · {row.stage ? stageLabel(row.stage) : "Interview"}
                </span>
              </Link>
            </li>
          ))}
        </AttentionList>

        <AttentionList
          headingId="attention-stalled"
          title="Stalled applications"
          count={stalled.length}
          emptyText="Nothing stalled. Nice."
          viewAllHref="/applications?stalled=1"
          viewAllLabel="stalled applications"
        >
          {stalled.slice(0, ATTENTION_ROW_LIMIT).map((row) => (
            <li key={row.applicationId}>
              <Link href={`/applications/${row.applicationId}`} className={ROW_CLASS}>
                <span className="truncate font-medium">{row.title}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {row.company} · {stageLabel(row.stage)}
                </span>
                <StalledChip days={row.daysSinceActivity} />
              </Link>
            </li>
          ))}
        </AttentionList>

        <AttentionList
          headingId="attention-errors"
          title="Automation issues"
          count={runErrors.length}
          emptyText="No failed automation runs in the last 7 days."
          viewAllHref="/runs"
          viewAllLabel="automation runs"
        >
          {runErrors.slice(0, ATTENTION_ROW_LIMIT).map((row) => (
            <li key={row.runId}>
              <Link href={`/runs/${row.runId}`} className={cn(ROW_CLASS, "border-danger/40")}>
                <span className="truncate font-medium">
                  {row.provider}
                  <span className="ml-2 text-xs font-normal text-muted-foreground">Failed</span>
                </span>
                <span className="line-clamp-2 text-xs text-muted-foreground">
                  {row.summary?.trim() || "Run failed without a message"}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {row.at ? formatRelative(row.at) : "Time not recorded"}
                </span>
              </Link>
            </li>
          ))}
        </AttentionList>
      </div>
    </DashboardCard>
  );
}
