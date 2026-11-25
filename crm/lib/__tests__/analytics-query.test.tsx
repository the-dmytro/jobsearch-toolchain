import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardBundle, useInsightsBundle } from "@/lib/analytics-query";
import type { DateRangeValue } from "@/lib/date-range-context";
import { qk } from "@/lib/query-keys";

const { createClient } = vi.hoisted(() => ({ createClient: vi.fn() }));
vi.mock("@/lib/supabase/client", () => ({ createClient }));

const APPLICATIONS = [
  { id: "a1", opportunity_id: null, organization_id: null, provider_id: null, status: "applied", current_stage: "Applied", applied_at: "2024-06-04T12:00:00.000Z", outcome: null, decline_reason: null, created_at: "2024-01-01T00:00:00.000Z", updated_at: "2024-01-01T00:00:00.000Z" },
  { id: "a2", opportunity_id: null, organization_id: null, provider_id: null, status: "applied", current_stage: "Phone screen", applied_at: "2024-06-10T12:00:00.000Z", outcome: null, decline_reason: null, created_at: "2024-01-01T00:00:00.000Z", updated_at: "2024-01-01T00:00:00.000Z" },
];

/** Tables read by the raw analytics load. Counts are kept per table to prove a single fetch. */
const TABLES: Record<string, unknown[]> = {
  applications: APPLICATIONS,
  application_events: [],
  interviews: [],
  opportunities: [],
  evaluations: [],
  communications: [],
  organizations: [],
  providers: [],
  automation_runs: [],
  automation_run_events: [],
};

let reads: Record<string, number> = {};

function stubClient() {
  return {
    from(table: string) {
      const state: { count: boolean; gt?: string; limit?: number } = { count: false };
      const resolve = () => {
        reads[table] = (reads[table] ?? 0) + 1;
        const rows = (TABLES[table] ?? []) as Array<{ id: string }>;
        if (state.count) return { data: null, count: rows.length, error: null };
        let data = [...rows].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        if (state.gt !== undefined) data = data.filter((row) => row.id > (state.gt as string));
        if (state.limit !== undefined) data = data.slice(0, state.limit);
        return { data, count: null, error: null };
      };
      const chain: unknown = new Proxy(
        {},
        {
          get(_target, prop) {
            if (prop === "then") {
              return (onFulfilled?: (value: unknown) => unknown, onRejected?: (reason: unknown) => unknown) =>
                Promise.resolve(resolve()).then(onFulfilled, onRejected);
            }
            return (...args: unknown[]) => {
              if (prop === "select" && (args[1] as { head?: boolean } | undefined)?.head) state.count = true;
              if (prop === "gt") state.gt = args[1] as string;
              if (prop === "limit") state.limit = args[0] as number;
              return chain;
            };
          },
        }
      );
      return chain;
    },
  };
}

const JUNE: DateRangeValue = {
  preset: "30d" as const,
  range: { start: new Date(2024, 5, 1, 0, 0, 0, 0), end: new Date(2024, 5, 30, 23, 59, 59, 999) },
};
const LAST_SEVEN: DateRangeValue = {
  preset: "7d" as const,
  range: { start: new Date(2024, 5, 14, 0, 0, 0, 0), end: new Date(2024, 5, 20, 23, 59, 59, 999) },
};

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  reads = {};
  createClient.mockReset();
  createClient.mockReturnValue(stubClient());
});

describe("shared analytics read", () => {
  it("reads each table once for the dashboard and insights, across two date ranges", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result, rerender } = renderHook(
      ({ value }: { value: DateRangeValue }) => ({
        dashboard: useDashboardBundle(value),
        insights: useInsightsBundle(value),
      }),
      { wrapper: wrapperFor(client), initialProps: { value: JUNE } }
    );

    await waitFor(() => expect(result.current.dashboard.data).toBeDefined());
    expect(result.current.dashboard.data?.kpis.appliedInRange).toBe(2);
    expect(result.current.insights.data).toBeDefined();

    const readsAfterFirstLoad = { ...reads };
    // Two rows in one page, then an empty page that ends the keyset walk. One load for both screens.
    expect(readsAfterFirstLoad.applications).toBe(2);

    // Switch to a different range. The bundles are recomputed in memory, with no request and no blank page.
    act(() => {
      rerender({ value: LAST_SEVEN });
    });
    expect(result.current.dashboard.data).toBeDefined();
    expect(result.current.insights.data).toBeDefined();
    expect(result.current.dashboard.data?.kpis.appliedInRange).toBe(0);
    expect(reads).toEqual(readsAfterFirstLoad);

    // Switching back is also free.
    act(() => {
      rerender({ value: JUNE });
    });
    expect(result.current.dashboard.data?.kpis.appliedInRange).toBe(2);
    expect(reads).toEqual(readsAfterFirstLoad);
  });

  it("keeps the raw read under one range-free key with a five minute stale time", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useDashboardBundle(JUNE), { wrapper: wrapperFor(client) });

    await waitFor(() => expect(result.current.data).toBeDefined());
    const query = client.getQueryCache().find({ queryKey: qk.analyticsRaw });
    expect(query).toBeDefined();
    expect(query?.observers[0]?.options.staleTime).toBe(5 * 60 * 1000);
    expect(query?.observers[0]?.options.placeholderData).toBeDefined();
  });
});
