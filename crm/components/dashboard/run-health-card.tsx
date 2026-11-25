"use client";

import Link from "next/link";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { Badge } from "@/components/ui/badge";
import { formatNumber, formatPercent, formatRelative } from "@/lib/format";
import type { Tables } from "@/types/database.types";

type RunHealthCardProps = {
  runs?: Tables<"automation_runs">[];
  runEvents?: Tables<"automation_run_events">[];
  status: CardStatus;
};

/** Compact summary: the latest run, the success rate across recent runs, and the last error. */
export function RunHealthCard({ runs, runEvents, status }: RunHealthCardProps) {
  const recentRuns = runs ?? [];
  const latest = recentRuns[0];
  const completed = recentRuns.filter((run) => run.status === "completed").length;
  const successRate = recentRuns.length > 0 ? completed / recentRuns.length : null;
  const lastError = (runEvents ?? []).find((event) => event.severity === "error");

  return (
    <DashboardCard
      title="Run health"
      description="Latest automation run, success rate across the most recent runs, and the last error."
      status={status}
      isEmpty={recentRuns.length === 0}
      emptyTitle="No automation runs yet"
      emptyDescription="Runs appear here once automation has run."
    >
      <dl className="grid gap-4 text-sm sm:grid-cols-3">
        <div className="min-w-0 space-y-1">
          <dt className="text-xs font-medium text-muted-foreground">Latest run</dt>
          <dd className="flex min-w-0 items-center gap-2">
            {latest ? (
              <>
                <Link
                  href={`/runs/${latest.id}`}
                  className="min-w-0 truncate font-medium underline-offset-4 hover:underline"
                >
                  {latest.run_key ?? latest.id.slice(0, 8)}
                </Link>
                <Badge variant={latest.status === "completed" ? "secondary" : "destructive"}>
                  {latest.status}
                </Badge>
              </>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </dd>
        </div>

        <div className="min-w-0 space-y-1">
          <dt className="text-xs font-medium text-muted-foreground">Success rate</dt>
          <dd className="font-semibold tabular-nums">
            {successRate == null ? "—" : formatPercent(successRate)}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              of {formatNumber(recentRuns.length)} recent runs
            </span>
          </dd>
        </div>

        <div className="min-w-0 space-y-1">
          <dt className="text-xs font-medium text-muted-foreground">Last error</dt>
          <dd className="min-w-0">
            {lastError ? (
              <p className="text-sm">
                <span className="line-clamp-2">{lastError.message ?? lastError.event_type}</span>
                <span className="block text-xs text-muted-foreground">
                  {formatRelative(lastError.created_at)}
                </span>
              </p>
            ) : (
              <span className="text-muted-foreground">No recent errors</span>
            )}
          </dd>
        </div>
      </dl>
    </DashboardCard>
  );
}
