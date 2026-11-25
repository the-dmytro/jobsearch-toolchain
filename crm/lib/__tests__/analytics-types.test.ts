import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  computeDashboardBundle,
  computeInsightsBundle,
  fetchDashboardBundle,
  fetchInsightsBundle,
  type DashboardBundle,
  type DashboardInput,
  type DateBounds,
  type InsightsInput,
} from "@/lib/analytics";
import type { Tables } from "@/types/database.types";

const { createClient } = vi.hoisted(() => ({ createClient: vi.fn() }));
vi.mock("@/lib/supabase/client", () => ({ createClient }));

/* ------------------------------------------------------------------ */
/* Fixtures                                                            */
/* ------------------------------------------------------------------ */

/** Fixed "now" so every relative date below is deterministic. */
const NOW = new Date("2024-06-20T12:00:00.000Z");

/**
 * June 2024 in local time, so week boundaries match the code under test in any timezone.
 * The previous period is May 2024.
 */
const RANGE: DateBounds = {
  start: new Date(2024, 5, 1, 0, 0, 0, 0),
  end: new Date(2024, 5, 30, 23, 59, 59, 999),
};

const STAMP = "2024-01-01T00:00:00.000Z";

function application(
  overrides: Partial<Tables<"applications">> & { id: string }
): Tables<"applications"> {
  return {
    opportunity_id: null,
    organization_id: null,
    provider_id: null,
    application_channel: null,
    status: "active",
    current_stage: "applied",
    applied_at: null,
    salary_requested_text: null,
    salary_requested_min: null,
    salary_requested_max: null,
    salary_requested_currency: null,
    outcome: null,
    decline_reason: null,
    passed: null,
    notes: null,
    metadata: {},
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

function event(
  overrides: Partial<Tables<"application_events">> & { id: string; application_id: string }
): Tables<"application_events"> {
  return {
    event_type: "note",
    event_at: null,
    title: null,
    description: null,
    metadata: {},
    created_at: STAMP,
    ...overrides,
  };
}

function interview(
  overrides: Partial<Tables<"interviews">> & { id: string; application_id: string }
): Tables<"interviews"> {
  return {
    organization_id: null,
    stage: null,
    scheduled_at: null,
    completed_at: null,
    meeting_url: null,
    result: null,
    feedback_summary: null,
    transcript_artifact_id: null,
    notes: null,
    metadata: {},
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

function run(overrides: Partial<Tables<"automation_runs">> & { id: string }): Tables<"automation_runs"> {
  return {
    provider_id: null,
    run_key: null,
    started_at: null,
    finished_at: null,
    status: "completed",
    report_artifact_id: null,
    report_email_sent: null,
    report_email_subject: null,
    source_items_count: 0,
    opportunities_count: 0,
    evaluations_count: 0,
    manual_review_count: 0,
    summary: null,
    metadata: {},
    created_at: STAMP,
    updated_at: STAMP,
    ...overrides,
  };
}

/**
 * Dashboard dataset (now = 2024-06-20 12:00Z):
 * - app-a  applied Jun 4, screening since Jun 14 (6 days), replied Jun 6, open
 * - app-b  applied Jun 10, declined Jun 18, interviewed Jun 5
 * - app-c  applied May 10, still applied, open, 41 days (updated_at is ignored)
 * - app-d  applied May 15, offer since Jun 1 (19 days), open
 * - app-e  applied Jun 1, withdrawn Jun 15 (fallback to updated_at), inbound message Jun 3
 * - app-f  applied May 20, declined May 25
 */
function dashboardInput(overrides: Partial<DashboardInput> = {}): DashboardInput {
  return {
    applications: [
      application({
        id: "app-a",
        opportunity_id: "opp-1",
        organization_id: "org-1",
        current_stage: "screening",
        applied_at: "2024-06-04T12:00:00.000Z",
        updated_at: "2024-06-14T12:00:00.000Z",
      }),
      application({
        id: "app-b",
        opportunity_id: "opp-3",
        organization_id: "org-2",
        provider_id: "prov-2",
        status: "declined",
        current_stage: "declined",
        outcome: "declined",
        applied_at: "2024-06-10T12:00:00.000Z",
      }),
      application({
        id: "app-c",
        opportunity_id: "opp-2",
        organization_id: "org-3",
        current_stage: "applied",
        applied_at: "2024-05-10T12:00:00.000Z",
        updated_at: "2024-06-19T12:00:00.000Z",
      }),
      application({
        id: "app-d",
        organization_id: "org-4",
        current_stage: "offer",
        applied_at: "2024-05-15T12:00:00.000Z",
      }),
      application({
        id: "app-e",
        organization_id: "org-1",
        status: "withdrawn",
        current_stage: "withdrawn",
        applied_at: "2024-06-01T12:00:00.000Z",
        updated_at: "2024-06-15T12:00:00.000Z",
      }),
      application({
        id: "app-f",
        opportunity_id: "opp-2",
        status: "declined",
        current_stage: "declined",
        outcome: "declined",
        applied_at: "2024-05-20T12:00:00.000Z",
        decline_reason: "Compensation too low",
      }),
    ],
    events: [
      event({
        id: "ev-a1",
        application_id: "app-a",
        event_type: "reply",
        event_at: "2024-06-06T12:00:00.000Z",
        title: "Recruiter replied",
      }),
      event({
        id: "ev-a2",
        application_id: "app-a",
        event_type: "stage_change",
        event_at: "2024-06-14T12:00:00.000Z",
        title: "Stage → screening",
      }),
      event({
        id: "ev-a3",
        application_id: "app-a",
        event_type: "follow_up",
        event_at: "2024-06-22T12:00:00.000Z",
        title: "Follow-up call",
      }),
      event({
        id: "ev-b1",
        application_id: "app-b",
        event_type: "stage_change",
        event_at: "2024-06-18T12:00:00.000Z",
        title: "Stage → declined",
      }),
      event({
        id: "ev-b2",
        application_id: "app-b",
        event_type: "note",
        event_at: null,
        created_at: "2024-06-02T12:00:00.000Z",
      }),
      event({
        id: "ev-d1",
        application_id: "app-d",
        event_type: "stage_change",
        event_at: "2024-06-01T12:00:00.000Z",
        title: "Stage → offer",
      }),
      event({
        id: "ev-f1",
        application_id: "app-f",
        event_type: "stage_change",
        event_at: "2024-05-25T12:00:00.000Z",
        title: "Stage → declined",
      }),
    ],
    interviews: [
      interview({
        id: "int-1",
        application_id: "app-a",
        stage: "onsite",
        scheduled_at: "2024-06-19T12:00:00.000Z",
      }),
      interview({
        id: "int-2",
        application_id: "app-a",
        stage: "onsite",
        scheduled_at: "2024-06-25T12:00:00.000Z",
      }),
      interview({
        id: "int-3",
        application_id: "app-c",
        stage: "screening",
        scheduled_at: "2024-06-29T12:00:00.000Z",
      }),
      interview({
        id: "int-4",
        application_id: "app-b",
        stage: "screening",
        scheduled_at: "2024-06-05T12:00:00.000Z",
      }),
    ],
    opportunities: [
      { id: "opp-1", title: "Staff Engineer", organization_id: "org-1", provider_id: "prov-1", created_at: "2024-06-03T12:00:00.000Z", seniority: null, compensation_min: null, compensation_max: null, compensation_currency: null },
      { id: "opp-2", title: "Platform Lead", organization_id: "org-3", provider_id: "prov-1", created_at: "2024-05-20T12:00:00.000Z", seniority: null, compensation_min: null, compensation_max: null, compensation_currency: null },
      { id: "opp-3", title: "Data Lead", organization_id: "org-2", provider_id: "prov-2", created_at: "2024-06-10T12:00:00.000Z", seniority: null, compensation_min: null, compensation_max: null, compensation_currency: null },
    ],
    evaluations: [
      { id: "eval-1", opportunity_id: "opp-1", score: 8, evaluated_at: "2024-06-05T12:00:00.000Z" },
      { id: "eval-2", opportunity_id: "opp-2", score: 5, evaluated_at: "2024-05-05T12:00:00.000Z" },
      { id: "eval-3", opportunity_id: "opp-3", score: 7, evaluated_at: "2024-06-11T12:00:00.000Z" },
    ],
    communications: [
      { id: "com-1", application_id: "app-e", direction: "inbound", sent_at: "2024-06-03T12:00:00.000Z", created_at: "2024-06-03T12:00:00.000Z" },
    ],
    organizations: [
      { id: "org-1", name: "Globex" },
      { id: "org-2", name: "Initech" },
      { id: "org-3", name: "Umbrella" },
      { id: "org-4", name: "Hooli" },
    ],
    providers: [
      { id: "prov-1", name: "Ashby", slug: "ashby" },
      { id: "prov-2", name: "Lever", slug: "lever" },
    ],
    recentRuns: [run({ id: "run-1", status: "completed" })],
    recentRunEvents: [],
    failedRuns: [
      run({ id: "run-f1", status: "failed", provider_id: "prov-1", started_at: "2024-06-19T12:00:00.000Z", summary: "feed returned 500" }),
      run({ id: "run-f2", status: "failed", started_at: "2024-06-01T12:00:00.000Z" }),
    ],
    ...overrides,
  };
}

function dashboard(input: DashboardInput = dashboardInput()): DashboardBundle {
  return computeDashboardBundle(input, RANGE, NOW);
}

/* ------------------------------------------------------------------ */
/* Dashboard computation                                               */
/* ------------------------------------------------------------------ */

describe("computeDashboardBundle KPIs", () => {
  it("counts applications, interviews and opportunities by their date rules", () => {
    const { kpis } = dashboard();

    expect(kpis.appliedInRange).toBe(3);
    expect(kpis.appliedPrevPeriod).toBe(3);
    // Future interviews (Jun 25, Jun 29) are excluded; the Jun 5 and Jun 19 ones count.
    expect(kpis.interviewsInRange).toBe(2);
    expect(kpis.interviewsPrev).toBe(0);
    expect(kpis.newOpportunities).toBe(2);
    expect(kpis.newOpportunitiesPrev).toBe(1);
  });

  it("reports the open-application delta against the end of the previous period", () => {
    const { kpis } = dashboard();

    expect(kpis.openApplications).toBe(3);
    // Open on May 31: app-c and app-d. app-f had already been declined by then.
    expect(kpis.openApplicationsPrev).toBe(2);
  });

  it("computes response rate as a 0..1 ratio with its sample size", () => {
    const { kpis } = dashboard();

    // app-a (reply), app-b (declined), app-e (inbound message) all responded.
    expect(kpis.responseRate).toEqual({ value: 1, n: 3 });
    // In May: app-d and app-f responded, app-c did not.
    expect(kpis.responseRatePrev.n).toBe(3);
    expect(kpis.responseRatePrev.value).toBeCloseTo(2 / 3);
  });

  it("averages scores for the range and the previous period, or null when there are none", () => {
    expect(dashboard().kpis.avgScore).toBe(7.5);
    expect(dashboard().kpis.avgScorePrev).toBe(5);

    const empty = computeDashboardBundle({ ...dashboardInput(), evaluations: [] }, RANGE, NOW);
    expect(empty.kpis.avgScore).toBeNull();
    expect(empty.kpis.avgScorePrev).toBeNull();
  });
});

describe("computeDashboardBundle days in stage", () => {
  it("uses the latest stage-change event, not updated_at", () => {
    const { pipelineAging } = dashboard();
    const byId = new Map(pipelineAging.map((row) => [row.applicationId, row]));

    // app-a changed stage on Jun 14, so 6 days; its updated_at is also Jun 14.
    expect(byId.get("app-a")?.daysInStage).toBe(6);
    // app-c has no events and was applied May 10, so 41 days. updated_at (Jun 19) is ignored.
    expect(byId.get("app-c")?.daysInStage).toBe(41);
    // app-d moved to offer on Jun 1 (from its event title), so 19 days.
    expect(byId.get("app-d")?.daysInStage).toBe(19);
  });

  it("orders the pipeline by days in stage, longest first, and leaves out closed applications", () => {
    const { pipelineAging } = dashboard();

    expect(pipelineAging.map((row) => row.applicationId)).toEqual(["app-c", "app-d", "app-a"]);
    expect(pipelineAging[0]).toMatchObject({ company: "Umbrella", title: "Platform Lead", stage: "applied" });
    expect(pipelineAging[1].stage).toBe("offer");
  });
});

describe("computeDashboardBundle weekly velocity", () => {
  it("uses Monday-anchored weeks, includes the partial edge week and clips to the range", () => {
    const { weeklyActivity } = dashboard();

    // Jun 1 is a Saturday, so the first bucket is the week of Mon May 27 (partial).
    expect(weeklyActivity.map((w) => w.weekStart)).toEqual([
      "2024-05-27",
      "2024-06-03",
      "2024-06-10",
      "2024-06-17",
      "2024-06-24",
    ]);
  });

  it("counts applied, responses, opportunities and interviews per week", () => {
    const series = dashboard().weeklyActivity;
    const week = (start: string) => series.find((w) => w.weekStart === start);

    // app-e applied on Jun 1 (inside range), so it belongs to the partial May 27 week.
    expect(week("2024-05-27")).toMatchObject({ applied: 1, responses: 1, opportunities: 0, interviews: 0 });
    // app-a applied, opp-1 created, the Jun 5 interview, replies on Jun 3 (inbound) and Jun 6.
    expect(week("2024-06-03")).toMatchObject({ applied: 1, responses: 2, opportunities: 1, interviews: 1 });
    expect(week("2024-06-10")).toMatchObject({ applied: 1, responses: 0, opportunities: 1, interviews: 0 });
    expect(week("2024-06-17")).toMatchObject({ applied: 0, responses: 1, opportunities: 0, interviews: 1 });
  });

  it("excludes interviews scheduled in the future", () => {
    const series = dashboard().weeklyActivity;
    const last = series[series.length - 1];

    // The Jun 25 and Jun 29 interviews are still ahead of "now".
    expect(last).toMatchObject({ weekStart: "2024-06-24", interviews: 0 });
    expect(series.reduce((sum, w) => sum + w.interviews, 0)).toBe(2);
  });
});

/**
 * Cohort of applications applied in June (RANGE). Each one reaches a different furthest step:
 * - c1 offer (current stage)           -> reaches offer
 * - c2 onsite, history through onsite  -> reaches final / onsite
 * - c3 declined after screening        -> keeps the furthest step before it (screening)
 * - c4 still applied, no history       -> applied only
 * - c5 applied in May                  -> outside the cohort; counts in the previous period
 * - c6 no applied_at, created in June  -> dated by created_at, reaches interview
 * - c7 outcome offer, stage applied    -> an offer outcome counts as reaching offer
 */
function cohortInput(): DashboardInput {
  const base = dashboardInput();
  return {
    ...base,
    applications: [
      application({ id: "c1", organization_id: "org-1", current_stage: "offer", applied_at: "2024-06-02T12:00:00.000Z" }),
      application({ id: "c2", organization_id: "org-1", current_stage: "onsite", applied_at: "2024-06-03T12:00:00.000Z" }),
      application({
        id: "c3",
        organization_id: "org-2",
        status: "declined",
        current_stage: "declined",
        outcome: "declined",
        applied_at: "2024-06-04T12:00:00.000Z",
      }),
      application({ id: "c4", organization_id: "org-3", current_stage: "applied", applied_at: "2024-06-05T12:00:00.000Z" }),
      application({ id: "c5", organization_id: "org-4", current_stage: "offer", applied_at: "2024-05-20T12:00:00.000Z" }),
      application({ id: "c6", organization_id: "org-1", current_stage: "tech_interview", applied_at: null, created_at: "2024-06-06T12:00:00.000Z" }),
      application({ id: "c7", organization_id: "org-2", current_stage: "applied", outcome: "offer", applied_at: "2024-06-07T12:00:00.000Z" }),
    ],
    events: [
      event({ id: "cev-2a", application_id: "c2", event_type: "stage_change", event_at: "2024-06-04T12:00:00.000Z", title: "Stage → screening" }),
      event({ id: "cev-2b", application_id: "c2", event_type: "stage_change", event_at: "2024-06-08T12:00:00.000Z", title: "Stage → tech_interview" }),
      event({ id: "cev-2c", application_id: "c2", event_type: "stage_change", event_at: "2024-06-12T12:00:00.000Z", title: "Stage → onsite" }),
      event({ id: "cev-3a", application_id: "c3", event_type: "stage_change", event_at: "2024-06-08T12:00:00.000Z", title: "Stage → screening" }),
      event({ id: "cev-3b", application_id: "c3", event_type: "stage_change", event_at: "2024-06-14T12:00:00.000Z", title: "Stage → declined" }),
    ],
    interviews: [],
  };
}

describe("computeDashboardBundle cohort funnel", () => {
  const cohort = () => dashboard(cohortInput());

  it("counts each step as the applications that reached that stage or a later one", () => {
    const steps = cohort().funnel.steps;

    expect(steps.map((step) => [step.key, step.count])).toEqual([
      ["applied", 6],
      ["screening", 5],
      ["interview", 4],
      ["final", 3],
      ["offer", 2],
    ]);
  });

  it("gives conversion as step over previous step, with the previous count as n", () => {
    const steps = cohort().funnel.steps;

    expect(steps[0].conversion).toBeNull();
    expect(steps[1].conversion).toEqual({ value: 5 / 6, n: 6 });
    expect(steps[2].conversion).toEqual({ value: 4 / 5, n: 5 });
    expect(steps[3].conversion).toEqual({ value: 3 / 4, n: 4 });
    expect(steps[4].conversion).toEqual({ value: 2 / 3, n: 3 });
  });

  it("never increases down the funnel and never converts above 100%", () => {
    for (const bundle of [cohort(), dashboard()]) {
      const steps = bundle.funnel.steps;
      for (let i = 1; i < steps.length; i += 1) {
        expect(steps[i].count).toBeLessThanOrEqual(steps[i - 1].count);
        const value = steps[i].conversion?.value;
        if (value !== null && value !== undefined) {
          expect(value).toBeLessThanOrEqual(1);
          expect(value).toBeGreaterThanOrEqual(0);
        }
      }
    }
  });

  it("keeps the furthest step a declined application reached before it closed", () => {
    const input = cohortInput();
    const declinedOnly = { ...input, applications: input.applications.filter((app) => app.id === "c3") };

    // Applied, then screening (reached before it was declined). Nothing further.
    expect(dashboard(declinedOnly).funnel.steps.map((step) => step.count)).toEqual([1, 1, 0, 0, 0]);
  });

  it("reports the in-range sourcing stats beside the funnel", () => {
    // Opportunities created in June are opp-1 and opp-3; both have an evaluation. Applied is the cohort.
    expect(dashboard().funnel.sourcing).toEqual({ opportunitiesFound: 2, opportunitiesEvaluated: 2, applied: 3 });
  });

  it("counts offers in range and in the previous period on the KPIs", () => {
    const { kpis } = cohort();

    expect(kpis.offersInRange).toBe(2);
    // c5 applied in May and reached an offer, so it counts in the previous period.
    expect(kpis.offersPrev).toBe(1);
  });
});

describe("computeDashboardBundle funnel and sources", () => {
  it("builds the cohort funnel from the applications applied in range", () => {
    const { funnel } = dashboard();

    // app-a, app-b and app-e applied in June. Only app-a reached a stage past applied (screening).
    expect(funnel.steps.map((step) => [step.key, step.count])).toEqual([
      ["applied", 3],
      ["screening", 1],
      ["interview", 0],
      ["final", 0],
      ["offer", 0],
    ]);
    expect(funnel.steps[1].conversion).toEqual({ value: 1 / 3, n: 3 });
    expect(funnel.steps[2].conversion).toEqual({ value: 0, n: 1 });
    expect(funnel.steps[3].conversion).toEqual({ value: null, n: 0 });
  });

  it("reports per-provider conversion with an unassigned bucket", () => {
    const { sourceEffectiveness } = dashboard();
    const bySlug = new Map(sourceEffectiveness.map((row) => [row.slug, row]));

    expect(bySlug.get("ashby")).toMatchObject({ opportunities: 1, applications: 1, applicationsWithInterview: 1 });
    expect(bySlug.get("ashby")?.appToInterview).toEqual({ value: 1, n: 1 });
    expect(bySlug.get("ashby")?.responseRate).toEqual({ value: 1, n: 1 });
    expect(bySlug.get("lever")).toMatchObject({ applications: 1, applicationsWithInterview: 1 });
    expect(bySlug.get("unassigned")).toMatchObject({ applications: 1, applicationsWithInterview: 0 });
    expect(bySlug.get("unassigned")?.appToInterview).toEqual({ value: 0, n: 1 });
  });
});

describe("computeDashboardBundle needs-attention data", () => {
  it("lists only interviews in the next seven days", () => {
    const { upcomingInterviews } = dashboard().attention;

    expect(upcomingInterviews).toEqual([
      {
        interviewId: "int-2",
        applicationId: "app-a",
        scheduledAt: "2024-06-25T12:00:00.000Z",
        stage: "onsite",
        company: "Globex",
      },
    ]);
  });

  it("lists stalled open applications over 14 days, longest first", () => {
    const { stalled } = dashboard().attention;

    expect(stalled.map((row) => [row.applicationId, row.daysInStage])).toEqual([
      ["app-c", 41],
      ["app-d", 19],
    ]);
    expect(stalled[1]).toMatchObject({ company: "Hooli", title: "Untitled role", stage: "offer" });
  });

  it("lists failed runs from the last seven days, with the provider name", () => {
    const { runErrors } = dashboard().attention;

    expect(runErrors).toEqual([
      {
        runId: "run-f1",
        startedAt: "2024-06-19T12:00:00.000Z",
        provider: "Ashby",
        summary: "feed returned 500",
      },
    ]);
  });

  it("keeps the upcoming list chronological and returns row totals", () => {
    const bundle = dashboard();

    expect(bundle.upcoming.map((item) => item.label)).toEqual([
      "Follow-up call",
      "Interview (onsite)",
      "Interview (screening)",
    ]);
    expect(bundle.totals).toEqual({
      applications: 6,
      opportunities: 3,
      interviews: 4,
      evaluations: 3,
      communications: 1,
      automationRuns: 1,
    });
  });
});

describe("computeDashboardBundle velocity inputs", () => {
  it("returns an empty weekly series when there is no dated activity", () => {
    const empty = computeDashboardBundle(
      {
        ...dashboardInput(),
        applications: [],
        events: [],
        interviews: [],
        opportunities: [],
        evaluations: [],
        communications: [],
      },
      RANGE,
      NOW
    );

    expect(empty.weeklyActivity).toEqual([]);
    expect(empty.kpis.responseRate).toEqual({ value: null, n: 0 });
    expect(empty.funnel.steps.every((step) => step.count === 0)).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* Insights computation                                                */
/* ------------------------------------------------------------------ */

const INSIGHTS_OPPS = [
  { id: "opp-1", title: "Staff Engineer", organization_id: null, provider_id: null, created_at: "2024-06-03T12:00:00.000Z", seniority: "Senior", compensation_min: 100, compensation_max: 140, compensation_currency: "usd" },
  { id: "opp-2", title: "Platform Lead", organization_id: null, provider_id: null, created_at: "2024-06-03T12:00:00.000Z", seniority: "senior", compensation_min: 90, compensation_max: 120, compensation_currency: "EUR" },
  { id: "opp-3", title: "Data Lead", organization_id: null, provider_id: null, created_at: "2024-06-04T12:00:00.000Z", seniority: "senior", compensation_min: 120, compensation_max: null, compensation_currency: "USD" },
  { id: "opp-4", title: "Tools", organization_id: null, provider_id: null, created_at: "2024-06-05T12:00:00.000Z", seniority: null, compensation_min: 50, compensation_max: 60, compensation_currency: null },
  { id: "opp-5", title: "Old role", organization_id: null, provider_id: null, created_at: "2024-05-01T12:00:00.000Z", seniority: "Senior", compensation_min: 1000, compensation_max: 1000, compensation_currency: "USD" },
];

function insightsInput(overrides: Partial<InsightsInput> = {}): InsightsInput {
  return {
    applications: [
      application({ id: "s1", opportunity_id: "opp-1", current_stage: "offer", applied_at: "2024-06-02T12:00:00.000Z" }),
      application({ id: "s2", opportunity_id: "opp-1", status: "declined", current_stage: "declined", outcome: "declined", decline_reason: " Salary ", applied_at: "2024-06-03T12:00:00.000Z" }),
      application({ id: "s3", opportunity_id: "opp-2", applied_at: "2024-06-04T12:00:00.000Z" }),
      application({ id: "s4", opportunity_id: "opp-3", status: "withdrawn", current_stage: "withdrawn", applied_at: "2024-06-04T12:00:00.000Z" }),
      application({ id: "s5", opportunity_id: "opp-2", status: "declined", current_stage: "declined", outcome: "declined", decline_reason: "Compensation", applied_at: "2024-05-01T12:00:00.000Z" }),
    ],
    interviews: [
      interview({ id: "ii-1", application_id: "s1", stage: "technical", result: "passed", scheduled_at: "2024-06-05T12:00:00.000Z" }),
      interview({ id: "ii-2", application_id: "s1", stage: "tech_interview", result: "Passed", scheduled_at: "2024-06-09T12:00:00.000Z" }),
      interview({ id: "ii-3", application_id: "s1", stage: "onsite", result: null, scheduled_at: "2024-06-25T12:00:00.000Z" }),
      interview({ id: "ii-4", application_id: "s1", stage: "onsite", result: null, scheduled_at: "2024-05-20T12:00:00.000Z" }),
    ],
    opportunities: INSIGHTS_OPPS,
    evaluations: [
      { id: "e1", opportunity_id: "opp-1", score: 8.5, evaluated_at: "2024-06-05T12:00:00.000Z" },
      { id: "e2", opportunity_id: "opp-1", score: 4, evaluated_at: "2024-06-06T12:00:00.000Z" },
      { id: "e3", opportunity_id: "opp-2", score: 6, evaluated_at: "2024-06-07T12:00:00.000Z" },
      { id: "e4", opportunity_id: "opp-4", score: 9.5, evaluated_at: "2024-06-08T12:00:00.000Z" },
      { id: "e5", opportunity_id: "opp-1", score: 2, evaluated_at: "2024-05-01T12:00:00.000Z" },
    ],
    ...overrides,
  };
}

function insights(input: InsightsInput = insightsInput()) {
  return computeInsightsBundle(input, RANGE, NOW);
}

describe("computeInsightsBundle score outcomes", () => {
  it("counts each evaluation once, using the best outcome across its applications", () => {
    const { scoreOutcomes } = insights();
    const bucket = (name: string) => scoreOutcomes.find((row) => row.bucket === name);

    // e1 has two applications (offer and declined) and counts once as an offer.
    expect(bucket("7-8")).toMatchObject({ evaluations: 1, withApplication: 1, offers: 1, declined: 0 });
    // e2 is a second evaluation of the same opportunity, so it also counts once.
    expect(bucket("3-4")).toMatchObject({ evaluations: 1, withApplication: 1, offers: 1 });
    expect(bucket("5-6")).toMatchObject({ evaluations: 1, withApplication: 1, open: 1, offers: 0 });
  });

  it("only includes evaluations inside the selected range", () => {
    const { scoreOutcomes } = insights();

    // e5 (score 2, May 1) is outside June and must not appear in the 0-2 bucket.
    expect(scoreOutcomes.find((row) => row.bucket === "0-2")).toBeUndefined();
    expect(scoreOutcomes.reduce((sum, row) => sum + row.evaluations, 0)).toBe(4);
  });

  it("reports offer rates as 0..1 with the number of evaluations that had an application", () => {
    const { scoreOutcomes } = insights();
    const bucket = (name: string) => scoreOutcomes.find((row) => row.bucket === name);

    expect(bucket("3-4")?.offerRate).toEqual({ value: 1, n: 1 });
    expect(bucket("9-10")?.offerRate).toEqual({ value: null, n: 0 });
    expect(bucket("9-10")?.avgScore).toBe(9.5);
  });
});

describe("computeInsightsBundle outcomes and reasons", () => {
  it("groups applications in range by outcome category", () => {
    const breakdown = insights().outcomeBreakdown;

    expect(breakdown).toHaveLength(4);
    expect(breakdown).toEqual(
      expect.arrayContaining([
        { outcome: "offer", label: "Offer", count: 1 },
        { outcome: "declined", label: "Declined", count: 1 },
        { outcome: "active", label: "Open", count: 1 },
        { outcome: "withdrawn", label: "Withdrawn", count: 1 },
      ])
    );
  });

  it("counts decline reasons for applications in range only, trimmed", () => {
    expect(insights().declineReasons).toEqual([{ reason: "Salary", count: 1 }]);
    expect(insights().declineOther).toBe(0);
  });

  it("keeps the top eight decline reasons and sums the rest into an other count", () => {
    const declined = Array.from({ length: 10 }, (_, index) =>
      application({
        id: `dr-${index}`,
        opportunity_id: "opp-1",
        status: "declined",
        current_stage: "declined",
        outcome: "declined",
        decline_reason: `Reason ${index + 1}`,
        applied_at: "2024-06-05T12:00:00.000Z",
      })
    );
    const { declineReasons, declineOther } = insights(insightsInput({ applications: declined }));

    expect(declineReasons).toHaveLength(8);
    expect(declineOther).toBe(2);
    expect(declineReasons.reduce((sum, row) => sum + row.count, 0) + declineOther).toBe(10);
  });

  it("reports interview results by normalised stage, in range by scheduled date", () => {
    const { interviewOutcomes } = insights();

    expect(interviewOutcomes).toEqual([
      { stage: "tech_interview", result: "passed", count: 2 },
      { stage: "onsite", result: "pending", count: 1 },
    ]);
  });
});

describe("computeInsightsBundle compensation", () => {
  it("groups by currency and seniority and never mixes currencies", () => {
    const { compensationBySeniority } = insights();

    expect(compensationBySeniority).toEqual([
      { currency: "USD", seniority: "senior", avgMin: 110, avgMax: 140, count: 2 },
      { currency: "EUR", seniority: "senior", avgMin: 90, avgMax: 120, count: 1 },
      { currency: "unknown", seniority: "unspecified", avgMin: 50, avgMax: 60, count: 1 },
    ]);
  });

  it("returns null averages when a group has no values for that bound", () => {
    const { compensationBySeniority } = computeInsightsBundle(
      insightsInput({
        opportunities: [
          { id: "x", title: "X", organization_id: null, provider_id: null, created_at: "2024-06-03T12:00:00.000Z", seniority: null, compensation_min: null, compensation_max: null, compensation_currency: "GBP" },
        ],
        evaluations: [],
      }),
      RANGE,
      NOW
    );

    expect(compensationBySeniority).toEqual([
      { currency: "GBP", seniority: "unspecified", avgMin: null, avgMax: null, count: 1 },
    ]);
  });
});

/* ------------------------------------------------------------------ */
/* Data loading                                                        */
/* ------------------------------------------------------------------ */

type Row = Record<string, unknown>;
type TableFixture = Row[] | { error: string };
type RangeCall = { table: string; range?: [number, number]; limit?: number };

/**
 * Stands in for a PostgREST builder. Supports `.range()` and `.limit()` the way the server
 * does, and ignores filters, which the code under test re-applies in memory.
 */
function stubClient(tables: Record<string, TableFixture>, calls: RangeCall[] = []) {
  return {
    from(table: string) {
      const call: RangeCall = { table };
      calls.push(call);
      const fixture = tables[table] ?? [];

      const resolve = () => {
        if (!Array.isArray(fixture)) {
          return { data: null, error: { message: fixture.error } };
        }
        let data = fixture;
        if (call.range) data = fixture.slice(call.range[0], call.range[1] + 1);
        if (call.limit !== undefined) data = fixture.slice(0, call.limit);
        return { data, error: null };
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
              if (prop === "range") call.range = [args[0] as number, args[1] as number];
              if (prop === "limit") call.limit = args[0] as number;
              return chain;
            };
          },
        }
      );
      return chain;
    },
  };
}

function applicationRows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) =>
    application({
      id: `bulk-${index}`,
      applied_at: "2024-06-05T12:00:00.000Z",
    }) as unknown as Row
  );
}

function allTables(overrides: Record<string, TableFixture> = {}): Record<string, TableFixture> {
  const input = dashboardInput();
  return {
    applications: input.applications as unknown as Row[],
    application_events: input.events as unknown as Row[],
    interviews: input.interviews as unknown as Row[],
    opportunities: input.opportunities as unknown as Row[],
    evaluations: input.evaluations as unknown as Row[],
    communications: input.communications as unknown as Row[],
    organizations: input.organizations as unknown as Row[],
    providers: input.providers as unknown as Row[],
    automation_runs: [...input.recentRuns, ...input.failedRuns] as unknown as Row[],
    automation_run_events: [],
    ...overrides,
  };
}

beforeEach(() => {
  createClient.mockReset();
  vi.useRealTimers();
});

describe("fetchDashboardBundle", () => {
  it("loads every application, not just the first 1000 rows", async () => {
    const calls: RangeCall[] = [];
    createClient.mockReturnValue(
      stubClient(allTables({ applications: applicationRows(1001) }), calls)
    );

    const bundle = await fetchDashboardBundle(RANGE);

    expect(bundle.totals.applications).toBe(1001);
    const appCalls = calls.filter((c) => c.table === "applications" && c.range);
    expect(appCalls.map((c) => c.range)).toEqual([
      [0, 999],
      [1000, 1999],
    ]);
  });

  it("surfaces a query error with its message", async () => {
    createClient.mockReturnValue(
      stubClient(allTables({ applications: { error: "permission denied" } }))
    );

    await expect(fetchDashboardBundle(RANGE)).rejects.toThrow("permission denied");
  });

  it("returns zeroed analytics when every table is empty", async () => {
    createClient.mockReturnValue(stubClient({}));

    const bundle = await fetchDashboardBundle(RANGE);

    expect(bundle.kpis.openApplications).toBe(0);
    expect(bundle.kpis.avgScore).toBeNull();
    expect(bundle.kpis.responseRate).toEqual({ value: null, n: 0 });
    expect(bundle.upcoming).toEqual([]);
    expect(bundle.attention).toEqual({ upcomingInterviews: [], stalled: [], runErrors: [] });
    expect(bundle.totals.applications).toBe(0);
  });
});

describe("fetchInsightsBundle", () => {
  it("loads every opportunity so compensation covers more than 1000 roles", async () => {
    const opportunities = Array.from({ length: 1001 }, (_, index) => ({
      id: `opp-${index}`,
      title: "Role",
      organization_id: null,
      provider_id: null,
      created_at: "2024-06-05T12:00:00.000Z",
      seniority: "senior",
      compensation_min: 100,
      compensation_max: 200,
      compensation_currency: "USD",
    }));
    createClient.mockReturnValue(stubClient({ opportunities }));

    const bundle = await fetchInsightsBundle(RANGE);

    expect(bundle.compensationBySeniority).toEqual([
      { currency: "USD", seniority: "senior", avgMin: 100, avgMax: 200, count: 1001 },
    ]);
  });

  it("surfaces the first query error", async () => {
    createClient.mockReturnValue(stubClient({ evaluations: { error: "view missing" } }));

    await expect(fetchInsightsBundle(RANGE)).rejects.toThrow("view missing");
  });
});
