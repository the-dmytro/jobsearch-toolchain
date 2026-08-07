import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchDashboardBundle,
  fetchInsightsBundle,
  type DashboardBundle,
  type DashboardKpis,
  type DateBounds,
  type InsightsBundle,
  type UpcomingItem,
} from "@/lib/analytics";

const { createClient } = vi.hoisted(() => ({ createClient: vi.fn() }));

vi.mock("@/lib/supabase/client", () => ({ createClient }));

type QueryResult = { data: unknown; error: { message: string } | null };

/** Stands in for a PostgREST builder: every method chains, awaiting yields the result. */
function queryStub(result: QueryResult) {
  const chain: unknown = new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === "then") {
          return (
            onFulfilled?: (value: QueryResult) => unknown,
            onRejected?: (reason: unknown) => unknown
          ) => Promise.resolve(result).then(onFulfilled, onRejected);
        }
        return () => chain;
      },
    }
  );
  return chain;
}

function mockSupabase(tables: Record<string, QueryResult>) {
  createClient.mockReturnValue({
    from: (table: string) => queryStub(tables[table] ?? { data: [], error: null }),
  });
}

const RANGE: DateBounds = {
  start: new Date("2024-06-01T00:00:00.000Z"),
  end: new Date("2024-06-30T23:59:59.999Z"),
};

const inFuture = (days: number) =>
  new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString();

const APPLICATIONS = [
  {
    id: "app-1",
    status: "active",
    current_stage: "screening",
    outcome: null,
    applied_at: "2024-06-10T09:00:00.000Z",
    created_at: "2024-06-10T09:00:00.000Z",
  },
  {
    id: "app-2",
    status: "declined",
    current_stage: "declined",
    outcome: "declined",
    applied_at: "2024-06-20T09:00:00.000Z",
    created_at: "2024-06-20T09:00:00.000Z",
  },
  {
    id: "app-3",
    status: "active",
    current_stage: "applied",
    outcome: null,
    applied_at: "2024-05-10T09:00:00.000Z",
    created_at: "2024-05-10T09:00:00.000Z",
  },
];

const FUNNEL = {
  opportunities_count: 40,
  evaluated_count: 24,
  applied_count: 12,
  interviewing_count: 4,
  offer_count: 1,
  opp_to_eval_pct: 60,
  eval_to_applied_pct: 50,
  applied_to_interview_pct: 33,
  interview_to_offer_pct: 25,
};

function dashboardTables(): Record<string, QueryResult> {
  return {
    v_funnel_summary: { data: FUNNEL, error: null },
    v_weekly_activity: {
      data: [
        { week_start: "2024-06-03", opportunities: 5, applications: 2, interviews: 1 },
        { week_start: "2024-06-10", opportunities: 3, applications: 1, interviews: 0 },
      ],
      error: null,
    },
    v_source_effectiveness: {
      data: [
        {
          provider_id: "p1",
          provider_slug: "ashby",
          provider_name: "Ashby",
          opportunities: 10,
          applications: 4,
          interviews: 2,
          offers: 1,
          app_to_interview_pct: 50,
        },
      ],
      error: null,
    },
    v_pipeline_aging: {
      data: [
        {
          application_id: "app-1",
          organization_name: "Globex",
          opportunity_title: "Staff Engineer",
          current_stage: "phone",
          status: "active",
          days_in_stage: 21,
          applied_at: "2024-06-10T09:00:00.000Z",
          updated_at: "2024-06-11T09:00:00.000Z",
        },
      ],
      error: null,
    },
    applications: { data: APPLICATIONS, error: null },
    application_events: {
      data: [
        {
          id: "ev-1",
          application_id: "app-1",
          event_type: "reply",
          event_at: "2024-06-12T09:00:00.000Z",
          title: "Recruiter replied",
        },
        {
          id: "ev-2",
          application_id: "app-3",
          event_type: "note",
          event_at: "2024-05-12T09:00:00.000Z",
          title: null,
        },
        {
          id: "ev-3",
          application_id: "app-1",
          event_type: "follow_up",
          event_at: inFuture(2),
          title: "Follow-up call",
        },
        {
          id: "ev-4",
          application_id: "app-2",
          event_type: "reminder",
          event_at: inFuture(3),
          title: null,
        },
      ],
      error: null,
    },
    interviews: {
      data: [
        {
          id: "int-1",
          application_id: "app-1",
          stage: "onsite",
          scheduled_at: inFuture(1),
          completed_at: null,
          created_at: "2024-06-14T09:00:00.000Z",
        },
        {
          id: "int-2",
          application_id: "app-1",
          stage: "screening",
          scheduled_at: "2024-06-15T09:00:00.000Z",
          completed_at: null,
          created_at: "2024-06-14T09:00:00.000Z",
        },
        {
          id: "int-3",
          application_id: "app-3",
          stage: "screening",
          scheduled_at: "2024-05-15T09:00:00.000Z",
          completed_at: null,
          created_at: "2024-05-14T09:00:00.000Z",
        },
      ],
      error: null,
    },
    opportunities: {
      data: [
        { id: "opp-1", created_at: "2024-06-05T09:00:00.000Z" },
        { id: "opp-2", created_at: "2024-05-05T09:00:00.000Z" },
      ],
      error: null,
    },
    evaluations: {
      data: [
        { id: "eval-1", score: 8, evaluated_at: "2024-06-05T09:00:00.000Z" },
        { id: "eval-2", score: 7, evaluated_at: "2024-06-06T09:00:00.000Z" },
        { id: "eval-3", score: null, evaluated_at: "2024-06-07T09:00:00.000Z" },
        { id: "eval-4", score: 5, evaluated_at: "2024-05-05T09:00:00.000Z" },
      ],
      error: null,
    },
    automation_runs: {
      data: [{ id: "run-1", run_key: "2024-06-30", status: "completed" }],
      error: null,
    },
    automation_run_events: {
      data: [{ id: "rev-1", event_type: "fetch", severity: "info", message: "ok" }],
      error: null,
    },
  };
}

beforeEach(() => {
  createClient.mockReset();
});

describe("fetchDashboardBundle", () => {
  it("derives KPIs for the requested range and the preceding one", async () => {
    mockSupabase(dashboardTables());

    const bundle = await fetchDashboardBundle(RANGE);

    const expected: DashboardKpis = {
      openApplications: 2,
      appliedInRange: 2,
      appliedPrevPeriod: 1,
      responseRate: 50,
      responseRatePrev: 0,
      interviewsInRange: 1,
      interviewsPrev: 1,
      newOpportunities: 1,
      newOpportunitiesPrev: 1,
      avgScore: 7.5,
      avgScorePrev: 5,
    };
    expect(bundle.kpis).toEqual(expected);
  });

  it("collects future interviews and events into a chronological upcoming list", async () => {
    mockSupabase(dashboardTables());

    const bundle = await fetchDashboardBundle(RANGE);

    expect(bundle.upcoming.map((item) => item.label)).toEqual([
      "Interview (onsite)",
      "Follow-up call",
      "reminder",
    ]);
    expect(bundle.upcoming[0].href).toBe("/interviews/int-1");
    expect(bundle.upcoming[1].href).toBe("/applications/app-1");

    const timestamps = bundle.upcoming.map((item: UpcomingItem) =>
      new Date(item.at).getTime()
    );
    expect(timestamps).toEqual([...timestamps].sort((a, b) => a - b));
  });

  it("passes view rows through untouched", async () => {
    mockSupabase(dashboardTables());

    const bundle: DashboardBundle = await fetchDashboardBundle(RANGE);

    expect(bundle.funnel).toEqual(FUNNEL);
    expect(bundle.weeklyActivity).toHaveLength(2);
    expect(bundle.sourceEffectiveness[0].provider_slug).toBe("ashby");
    expect(bundle.pipelineAging[0].days_in_stage).toBe(21);
    expect(bundle.runs).toHaveLength(1);
    expect(bundle.runEvents).toHaveLength(1);
  });

  it("tolerates every query returning nothing", async () => {
    mockSupabase({ v_funnel_summary: { data: null, error: null } });

    const bundle = await fetchDashboardBundle(RANGE);

    expect(bundle.funnel).toBeNull();
    expect(bundle.upcoming).toEqual([]);
    expect(bundle.kpis.openApplications).toBe(0);
    expect(bundle.kpis.responseRate).toBe(0);
    expect(bundle.kpis.avgScore).toBe(0);
  });

  it("surfaces the first query error", async () => {
    mockSupabase({
      ...dashboardTables(),
      applications: { data: null, error: { message: "permission denied" } },
    });

    await expect(fetchDashboardBundle(RANGE)).rejects.toThrow("permission denied");
  });
});

describe("fetchInsightsBundle", () => {
  const tables: Record<string, QueryResult> = {
    v_score_outcomes: {
      data: [
        {
          score_bucket: "8-10",
          evaluation_count: 5,
          offer_count: 1,
          resolved_count: 4,
          avg_score: 8.6,
        },
      ],
      error: null,
    },
    applications: {
      data: [
        { id: "a1", outcome: "declined", decline_reason: "salary" },
        { id: "a2", outcome: "declined", decline_reason: "salary" },
        { id: "a3", outcome: "offer", decline_reason: null },
        { id: "a4", outcome: "  ", decline_reason: "   " },
      ],
      error: null,
    },
    opportunities: {
      data: [
        { id: "o1", seniority: "Senior", compensation_min: 100, compensation_max: 140 },
        { id: "o2", seniority: "senior", compensation_min: 120, compensation_max: null },
        { id: "o3", seniority: null, compensation_min: null, compensation_max: null },
      ],
      error: null,
    },
    interviews: {
      data: [
        { id: "i1", stage: "Onsite", result: "passed" },
        { id: "i2", stage: "onsite", result: "passed" },
        { id: "i3", stage: "screening", result: null },
      ],
      error: null,
    },
  };

  it("aggregates outcomes, decline reasons, compensation and interview results", async () => {
    mockSupabase(tables);

    const bundle: InsightsBundle = await fetchInsightsBundle(RANGE);

    expect(bundle.scoreOutcomes[0].score_bucket).toBe("8-10");
    expect(bundle.outcomeBreakdown).toEqual([
      { outcome: "declined", count: 2 },
      { outcome: "offer", count: 1 },
    ]);
    expect(bundle.declineReasons).toEqual([{ reason: "salary", count: 2 }]);
    expect(bundle.compensationBySeniority).toEqual([
      { seniority: "senior", avgMin: 110, avgMax: 140, count: 2 },
      { seniority: "unspecified", avgMin: 0, avgMax: 0, count: 1 },
    ]);
    expect(bundle.interviewOutcomes).toEqual([
      { stage: "onsite", result: "passed", count: 2 },
      { stage: "screening", result: "pending", count: 1 },
    ]);
  });

  it("surfaces the first query error", async () => {
    mockSupabase({
      ...tables,
      v_score_outcomes: { data: null, error: { message: "view missing" } },
    });

    await expect(fetchInsightsBundle(RANGE)).rejects.toThrow("view missing");
  });
});
