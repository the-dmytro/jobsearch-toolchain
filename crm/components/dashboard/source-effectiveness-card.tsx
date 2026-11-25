"use client";

import { useState } from "react";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { Button } from "@/components/ui/button";
import type { SourceEffectiveness } from "@/lib/analytics";
import { formatNumber, formatPercent } from "@/lib/format";

/** Sources with fewer applications than this sit behind "Show all". */
export const MIN_SOURCE_APPLICATIONS = 3;

type SourceEffectivenessCardProps = {
  sources?: SourceEffectiveness[];
  status: CardStatus;
};

function byResponseRate(a: SourceEffectiveness, b: SourceEffectiveness): number {
  const rateA = a.responseRate.value ?? -1;
  const rateB = b.responseRate.value ?? -1;
  return rateB - rateA || b.applications - a.applications || a.name.localeCompare(b.name);
}

/**
 * Response rate per source, as horizontal bars sorted by rate. Each bar is labelled with its
 * rate and the number of applications behind it, so a rate on a small sample is never shown alone.
 */
export function SourceEffectivenessCard({ sources, status }: SourceEffectivenessCardProps) {
  const [showAll, setShowAll] = useState(false);

  const withApplications = (sources ?? []).filter((source) => source.applications > 0);
  const shown = withApplications
    .filter((source) => source.applications >= MIN_SOURCE_APPLICATIONS)
    .sort(byResponseRate);
  const hidden = withApplications
    .filter((source) => source.applications < MIN_SOURCE_APPLICATIONS)
    .sort((a, b) => b.applications - a.applications || a.name.localeCompare(b.name));
  const visible = showAll ? [...shown, ...hidden] : shown;

  const footer =
    hidden.length > 0 ? (
      <div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={showAll}
          onClick={() => setShowAll((value) => !value)}
        >
          {showAll
            ? "Show fewer sources"
            : `Show all ${formatNumber(withApplications.length)} sources`}
        </Button>
      </div>
    ) : null;

  return (
    <DashboardCard
      title="Source effectiveness"
      description="Share of applications that got any response, by source. Sources with fewer than 3 applications are hidden."
      status={status}
      isEmpty={withApplications.length === 0}
      emptyTitle="No applications from a source yet"
      emptyDescription="Sources appear here once applications in the range are linked to one."
      footer={footer}
    >
      {shown.length === 0 && !showAll ? (
        <p className="text-sm text-muted-foreground">
          No source has {MIN_SOURCE_APPLICATIONS} or more applications in this range yet.
        </p>
      ) : null}
      <ul className="space-y-3" aria-label="Response rate by source">
        {visible.map((source) => {
          const pct = source.responseRate.value == null ? 0 : source.responseRate.value * 100;
          return (
            <li key={source.providerId ?? "unassigned"} className="space-y-1">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate font-medium">{source.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {source.responseRate.value == null
                    ? "No applications"
                    : `${formatPercent(source.responseRate.value)} of ${formatNumber(source.applications)} apps`}
                </span>
              </div>
              <div aria-hidden="true" className="h-2 overflow-hidden rounded-sm bg-muted">
                <div className="h-full rounded-sm bg-chart-1" style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </DashboardCard>
  );
}
