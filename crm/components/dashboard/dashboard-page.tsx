"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCwIcon } from "lucide-react";

import { PageHeader } from "@/components/crm/page-header";
import { ErrorBoundary } from "@/components/crm/error-boundary";
import { FunnelCard } from "@/components/dashboard/funnel-card";
import { KpiRow } from "@/components/dashboard/kpi-row";
import { PipelineAgingCard } from "@/components/dashboard/pipeline-aging-card";
import { RunHealthCard } from "@/components/dashboard/run-health-card";
import { SourceEffectivenessCard } from "@/components/dashboard/source-effectiveness-card";
import { UpcomingCard } from "@/components/dashboard/upcoming-card";
import { VelocityCard } from "@/components/dashboard/velocity-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchDashboardBundle } from "@/lib/analytics";
import { useDateRange } from "@/lib/date-range-context";
import { isDemoMode } from "@/lib/demo";
import { qk } from "@/lib/query-keys";

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-lg" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-96 rounded-lg" />
        <Skeleton className="h-96 rounded-lg" />
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { value: dateRange } = useDateRange();
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: qk.dashboard(dateRange),
    queryFn: () => fetchDashboardBundle(dateRange.range),
  });

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Dashboard"
        description={
          isDemoMode()
            ? "Synthetic demo data for evaluation (NEXT_PUBLIC_DEMO_MODE)."
            : "Analytics from Postgres views with RLS."
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RefreshCwIcon className={isFetching ? "size-4 animate-spin" : "size-4"} />
            Refresh
          </Button>
        }
      />

      {isLoading ? <DashboardSkeleton /> : null}

      {isError ? (
        <p className="text-destructive">
          Failed to load dashboard: {error instanceof Error ? error.message : "Unknown error"}
        </p>
      ) : null}

      {data ? (
        <ErrorBoundary title="Dashboard failed to render">
          <div className="flex flex-col gap-6">
            <KpiRow kpis={data.kpis} weeklyActivity={data.weeklyActivity} />

            <div className="grid gap-4 lg:grid-cols-2">
              <FunnelCard funnel={data.funnel} />
              <VelocityCard weeklyActivity={data.weeklyActivity} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <SourceEffectivenessCard sources={data.sourceEffectiveness} />
              <PipelineAgingCard pipeline={data.pipelineAging} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <UpcomingCard upcoming={data.upcoming} />
              <RunHealthCard runs={data.runs} runEvents={data.runEvents} />
            </div>
          </div>
        </ErrorBoundary>
      ) : null}
    </div>
  );
}
