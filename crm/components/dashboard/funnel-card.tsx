"use client";

import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import type { FunnelStep, FunnelSummary } from "@/lib/analytics";
import { formatNumber, formatPercent } from "@/lib/format";

type FunnelCardProps = {
  funnel?: FunnelSummary;
  status: CardStatus;
};

function conversionText(step: FunnelStep, previous: FunnelStep): string {
  const conversion = step.conversion;
  if (!conversion || conversion.value == null) {
    return `No applications at ${previous.label.toLowerCase()} yet`;
  }
  return `${formatPercent(conversion.value)} of ${previous.label.toLowerCase()} (${formatNumber(step.count)} of ${formatNumber(conversion.n)})`;
}

/**
 * Cohort funnel: horizontal bars with direct count labels. Each bar counts applications
 * that reached that stage or a later one, so bars only shrink as you go down. The text
 * list is the accessible alternative to the bars.
 */
export function FunnelCard({ funnel, status }: FunnelCardProps) {
  const steps = funnel?.steps ?? [];
  const applied = steps[0]?.count ?? 0;
  const sourcing = funnel?.sourcing;

  return (
    <DashboardCard
      title="Funnel"
      description="Applications applied in range, counted by the furthest stage each one reached."
      status={status}
      isEmpty={funnel !== undefined && applied === 0}
      emptyTitle="No applications in this range"
      emptyDescription="Applications dated in the selected range appear here as they are counted."
      footer={
        sourcing ? (
          <p className="border-t pt-3 text-xs text-muted-foreground tabular-nums">
            Sourcing in range: {formatNumber(sourcing.opportunitiesFound)} opportunities found,{" "}
            {formatNumber(sourcing.opportunitiesEvaluated)} evaluated, {formatNumber(sourcing.applied)} applied.
          </p>
        ) : null
      }
    >
      <ol className="space-y-3" aria-label="Funnel steps, applications and conversion">
        {steps.map((step, index) => {
          const width = applied > 0 ? (step.count / applied) * 100 : 0;
          return (
            <li key={step.key} className="space-y-1">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium">{step.label}</span>
                <span className="font-semibold tabular-nums">{formatNumber(step.count)}</span>
              </div>
              <div aria-hidden="true" className="h-2 overflow-hidden rounded-sm bg-muted">
                <div className="h-full rounded-sm bg-chart-1" style={{ width: `${width}%` }} />
              </div>
              <p className="text-xs text-muted-foreground tabular-nums">
                {index === 0 ? "Starting point" : conversionText(step, steps[index - 1])}
              </p>
            </li>
          );
        })}
      </ol>
    </DashboardCard>
  );
}
