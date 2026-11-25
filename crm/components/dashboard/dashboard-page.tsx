"use client";

import { RefreshCwIcon } from "lucide-react";

import { ErrorBoundary } from "@/components/crm/error-boundary";
import { PageHeader } from "@/components/crm/page-header";
import { AttentionCard } from "@/components/dashboard/attention-card";
import type { CardStatus } from "@/components/dashboard/dashboard-card";
import { FunnelCard } from "@/components/dashboard/funnel-card";
import { hasPreviousPeriod, rangePhrase } from "@/components/dashboard/labels";
import { KpiRow } from "@/components/dashboard/kpi-row";
import { PipelineAgingCard } from "@/components/dashboard/pipeline-aging-card";
import { RunHealthCard } from "@/components/dashboard/run-health-card";
import { SourceEffectivenessCard } from "@/components/dashboard/source-effectiveness-card";
import { WeeklyActivityCard } from "@/components/dashboard/weekly-activity-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDashboardBundle } from "@/lib/analytics-query";
import { type DateRangeValue, useDateRange } from "@/lib/date-range-context";
import { isDemoMode } from "@/lib/demo";

function rangeSentence(value: DateRangeValue): string {
  const phrase = rangePhrase(value);
  const sentence = phrase.charAt(0).toUpperCase() + phrase.slice(1);
  return hasPreviousPeriod(value)
    ? `${sentence}. Changes compare with the same length of time before.`
    : `${sentence}. Changes are not shown because there is no earlier period.`;
}

export function DashboardPage() {
  const { value: dateRange } = useDateRange();
  const query = useDashboardBundle(dateRange);
  const data = query.data;

  // Every card receives the same load state, so each one shows its own skeleton, error or empty state.
  const status: CardStatus = {
    loading: query.isPending,
    error: query.isError ? query.error : undefined,
    onRetry: () => void query.refetch(),
  };

  return (
    <div className="flex min-w-0 flex-col gap-8">
      <PageHeader
        title="Dashboard"
        description={rangeSentence(dateRange)}
        actions={
          <>
            {isDemoMode() ? <Badge variant="outline">Demo data</Badge> : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
            >
              <RefreshCwIcon className={query.isFetching ? "size-4 animate-spin" : "size-4"} />
              Refresh
            </Button>
          </>
        }
      />

      <ErrorBoundary title="Dashboard failed to render">
        <div className="grid min-w-0 gap-4">
          <AttentionCard attention={data?.attention} status={status} />

          <KpiRow
            kpis={data?.kpis}
            weeklyActivity={data?.weeklyActivity}
            status={status}
            showDeltas={hasPreviousPeriod(dateRange)}
          />

          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <FunnelCard funnel={data?.funnel} status={status} />
            <WeeklyActivityCard weeklyActivity={data?.weeklyActivity} status={status} />
          </div>

          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <SourceEffectivenessCard sources={data?.sourceEffectiveness} status={status} />
            <PipelineAgingCard pipeline={data?.pipelineAging} status={status} />
          </div>

          <RunHealthCard runs={data?.runs} runEvents={data?.runEvents} status={status} />
        </div>
      </ErrorBoundary>
    </div>
  );
}
