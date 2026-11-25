import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  computeDashboardBundle,
  computeInsightsBundle,
  fetchRawAnalytics,
  resolveRange,
  type DashboardBundle,
  type InsightsBundle,
  type RawAnalytics,
} from "@/lib/analytics";
import type { DateRangeValue } from "@/lib/date-range-context";
import { qk } from "@/lib/query-keys";

/** The raw analytics read is reused for five minutes before a background refetch. */
export const RAW_ANALYTICS_STALE_MS = 5 * 60 * 1000;

/** The range-free read shared by the dashboard and insights. */
export function useRawAnalytics() {
  return useQuery({
    queryKey: qk.analyticsRaw,
    queryFn: fetchRawAnalytics,
    staleTime: RAW_ANALYTICS_STALE_MS,
    placeholderData: keepPreviousData,
  });
}

type Computed<T> = {
  data: T | undefined;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  isFetching: boolean;
  refetch: () => Promise<unknown>;
};

/** Dashboard bundle for a date range. Computed in memory, so a range change costs no request. */
export function useDashboardBundle(value: DateRangeValue): Computed<DashboardBundle> {
  const raw = useRawAnalytics();
  const data = useMemo(
    () =>
      raw.data
        ? computeDashboardBundle(raw.data, resolveRange(value, raw.data), new Date())
        : undefined,
    [raw.data, value]
  );
  return pickState(raw, data);
}

/** Insights bundle for a date range. Shares the raw read with the dashboard. */
export function useInsightsBundle(value: DateRangeValue): Computed<InsightsBundle> {
  const raw = useRawAnalytics();
  const data = useMemo(
    () =>
      raw.data
        ? computeInsightsBundle(raw.data, resolveRange(value, raw.data), new Date())
        : undefined,
    [raw.data, value]
  );
  return pickState(raw, data);
}

function pickState<T>(
  raw: {
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    isFetching: boolean;
    refetch: () => Promise<unknown>;
  },
  data: T | undefined
): Computed<T> {
  return {
    data,
    isPending: raw.isPending,
    isError: raw.isError,
    error: raw.error,
    isFetching: raw.isFetching,
    refetch: raw.refetch,
  };
}

export type { RawAnalytics };
