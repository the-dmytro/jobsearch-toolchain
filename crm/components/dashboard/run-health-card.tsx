"use client";

import Link from "next/link";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { Badge } from "@/components/ui/badge";
import type { RunError } from "@/lib/analytics";
import { formatNumber, formatRelative } from "@/lib/format";
import type { Tables } from "@/types/database.types";

type RunHealthCardProps = {
  /** The most recent runs, newest first by runTime. */
  runs?: Tables<"automation_runs">[];
  /** The latest failed run, or null. */
  lastFailure?: RunError | null;
  status: CardStatus;
};

function statusOf(run: Tables<"automation_runs">): string {
  return run.status.trim().toLowerCase();
}

function isFailed(run: Tables<"automation_runs">): boolean {
  return statusOf(run) === "failed";
}

/** Statuses of a run that has ended. Partial runs ended with warnings, not errors. */
const ENDED_STATUSES = new Set(["completed", "partial", "failed"]);

/** Compact summary: the latest run, how many recent runs finished without errors, and the last failure. */
export function RunHealthCard({ runs, lastFailure, status }: RunHealthCardProps) {
  const recentRuns = runs ?? [];
  const latest = recentRuns[0];
  // Runs still going (or with an unknown status) are left out of both numbers.
  const endedRuns = recentRuns.filter((run) => ENDED_STATUSES.has(statusOf(run)));
  const finishedWithoutErrors = endedRuns.filter((run) => !isFailed(run)).length;

  return (
    <DashboardCard
      title="Run health"
      description="Latest automation run, how many recent runs finished without errors, and the last failed run."
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
                <Badge variant={isFailed(latest) ? "destructive" : "secondary"}>{latest.status}</Badge>
              </>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </dd>
        </div>

        <div className="min-w-0 space-y-1">
          <dt className="text-xs font-medium text-muted-foreground">Finished without errors</dt>
          <dd className="font-semibold tabular-nums">
            {endedRuns.length === 0
              ? "—"
              : `${formatNumber(finishedWithoutErrors)} of ${formatNumber(endedRuns.length)}`}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              recent runs (partial runs count as finished)
            </span>
          </dd>
        </div>

        <div className="min-w-0 space-y-1">
          <dt className="text-xs font-medium text-muted-foreground">Last error</dt>
          <dd className="min-w-0">
            {lastFailure ? (
              <p className="text-sm">
                <Link
                  href={`/runs/${lastFailure.runId}`}
                  className="line-clamp-2 underline-offset-4 hover:underline"
                >
                  {lastFailure.summary?.trim() || `${lastFailure.provider} failed without a message`}
                </Link>
                <span className="block text-xs text-muted-foreground">
                  {lastFailure.at ? formatRelative(lastFailure.at) : "Time not recorded"}
                </span>
              </p>
            ) : (
              <span className="text-muted-foreground">No failed runs</span>
            )}
          </dd>
        </div>
      </dl>
    </DashboardCard>
  );
}
