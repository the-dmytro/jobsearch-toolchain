import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AttentionCard } from "@/components/dashboard/attention-card";
import { DashboardCard } from "@/components/dashboard/dashboard-card";
import { FunnelCard } from "@/components/dashboard/funnel-card";
import { KpiRow } from "@/components/dashboard/kpi-row";
import { PipelineAgingCard } from "@/components/dashboard/pipeline-aging-card";
import { RunHealthCard } from "@/components/dashboard/run-health-card";
import { SourceEffectivenessCard } from "@/components/dashboard/source-effectiveness-card";
import { WeeklyActivityCard } from "@/components/dashboard/weekly-activity-card";
import type {
  AttentionBundle,
  DashboardKpis,
  FunnelSummary,
  PipelineAgingRow,
  SourceEffectiveness,
  WeeklyActivityPoint,
} from "@/lib/analytics";
import { formatDuration } from "@/lib/format";
import type { Tables } from "@/types/database.types";

const READY = { loading: false } as const;

const EMPTY_KPIS: DashboardKpis = {
  openApplications: 0,
  openApplicationsPrev: 0,
  appliedInRange: 0,
  appliedPrevPeriod: 0,
  responseRate: { value: null, n: 0 },
  responseRatePrev: { value: null, n: 0 },
  interviewsInRange: 0,
  interviewsPrev: 0,
  offersInRange: 0,
  offersPrev: 0,
  newOpportunities: 0,
  newOpportunitiesPrev: 0,
  avgScore: null,
  avgScorePrev: null,
};

const KPIS: DashboardKpis = {
  openApplications: 12,
  openApplicationsPrev: 12,
  appliedInRange: 9,
  appliedPrevPeriod: 4,
  responseRate: { value: 0.44, n: 41 },
  responseRatePrev: { value: 0.5, n: 40 },
  interviewsInRange: 1,
  interviewsPrev: 3,
  offersInRange: 2,
  offersPrev: 1,
  newOpportunities: 17,
  newOpportunitiesPrev: 11,
  avgScore: 7.4,
  avgScorePrev: 6.9,
};

const WEEKLY_ACTIVITY: WeeklyActivityPoint[] = [
  { weekStart: "2024-06-03", opportunities: 8, applied: 4, responses: 2, interviews: 1 },
  { weekStart: "2024-06-10", opportunities: 5, applied: 3, responses: 1, interviews: 2 },
  { weekStart: "2024-06-17", opportunities: 4, applied: 2, responses: 0, interviews: 0 },
];

/** Cohort funnel: applied 6, then cumulative counts at each later step. */
const FUNNEL: FunnelSummary = {
  steps: [
    { key: "applied", label: "Applied", count: 6, conversion: null },
    { key: "screening", label: "Screening", count: 4, conversion: { value: 4 / 6, n: 6 } },
    { key: "interview", label: "Interview", count: 2, conversion: { value: 0.5, n: 4 } },
    { key: "final", label: "Final / onsite", count: 1, conversion: { value: 0.5, n: 2 } },
    { key: "offer", label: "Offer", count: 0, conversion: { value: 0, n: 1 } },
  ],
  sourcing: { opportunitiesFound: 5, opportunitiesEvaluated: 4, applied: 6 },
};

const SOURCES: SourceEffectiveness[] = [
  {
    providerId: "p1",
    slug: "ashby",
    name: "Ashby",
    opportunities: 20,
    applications: 8,
    applicationsWithInterview: 4,
    applicationsWithResponse: 6,
    responseRate: { value: 0.75, n: 8 },
    offers: 1,
    appToInterview: { value: 0.5, n: 8 },
  },
  {
    providerId: "p2",
    slug: "lever",
    name: "Lever",
    opportunities: 12,
    applications: 5,
    applicationsWithInterview: 1,
    applicationsWithResponse: 2,
    responseRate: { value: 0.4, n: 5 },
    offers: 0,
    appToInterview: { value: 0.2, n: 5 },
  },
  {
    providerId: "p3",
    slug: "greenhouse",
    name: "Greenhouse",
    opportunities: 3,
    applications: 2,
    applicationsWithInterview: 0,
    applicationsWithResponse: 2,
    responseRate: { value: 1, n: 2 },
    offers: 0,
    appToInterview: { value: 0, n: 2 },
  },
  {
    providerId: null,
    slug: "unassigned",
    name: "Unassigned",
    opportunities: 4,
    applications: 0,
    applicationsWithInterview: 0,
    applicationsWithResponse: 0,
    responseRate: { value: null, n: 0 },
    offers: 0,
    appToInterview: { value: null, n: 0 },
  },
];

const PIPELINE: PipelineAgingRow[] = [
  {
    applicationId: "app-1",
    company: "Globex",
    title: "Staff Engineer",
    stage: "screening",
    daysSinceActivity: 21,
    appliedAt: "2024-06-01T09:00:00.000Z",
  },
  {
    applicationId: "app-2",
    company: "Initech",
    title: "Platform Lead",
    stage: "onsite",
    daysSinceActivity: 3,
    appliedAt: "2024-06-18T09:00:00.000Z",
  },
];

const FUTURE = (days: number) => new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString();

const ATTENTION: AttentionBundle = {
  upcomingInterviews: [
    { interviewId: "int-1", applicationId: "app-1", scheduledAt: FUTURE(1), stage: "onsite", company: "Globex" },
    { interviewId: "int-2", applicationId: "app-2", scheduledAt: FUTURE(2), stage: null, company: "Initech" },
  ],
  stalled: [
    { applicationId: "app-1", company: "Globex", title: "Staff Engineer", stage: "screening", daysSinceActivity: 21 },
    { applicationId: "app-9", company: "Umbrella", title: "Data Lead", stage: "applied", daysSinceActivity: 16 },
  ],
  runErrors: [
    {
      runId: "run-f1",
      at: "2024-06-19T12:00:00.000Z",
      provider: "Ashby",
      summary: "feed returned 500",
    },
  ],
};

const NO_ATTENTION: AttentionBundle = { upcomingInterviews: [], stalled: [], runErrors: [] };

function makeRun(overrides: Partial<Tables<"automation_runs">>): Tables<"automation_runs"> {
  return {
    id: "00000000-0000-4000-8000-000000000000",
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
    created_at: "2024-06-30T09:00:00.000Z",
    updated_at: "2024-06-30T09:00:00.000Z",
    ...overrides,
  };
}

const RUNS: Tables<"automation_runs">[] = [
  makeRun({ id: "run-1", run_key: "2024-06-30-ashby", status: "completed" }),
  makeRun({ id: "run-2", run_key: "2024-06-29-lever", status: "failed" }),
];

const LAST_FAILURE = { runId: "run-2", at: "2024-06-29T09:00:00.000Z", provider: "Lever", summary: "feed returned 500" };

describe("DashboardCard states", () => {
  it("replaces the card with a labelled skeleton while loading", () => {
    render(
      <FunnelCard status={{ loading: true }} />
    );

    expect(screen.getByRole("status", { name: "Loading funnel" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Funnel" })).not.toBeInTheDocument();
  });

  it("shows a friendly error with a retry button, never the raw message", async () => {
    const onRetry = vi.fn();
    render(
      <FunnelCard status={{ loading: false, error: new Error("relation does not exist"), onRetry }} />
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load funnel");
    expect(screen.queryByText(/relation does not exist/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders an empty state inside a card when the card has nothing to show", () => {
    render(
      <DashboardCard title="Example" description="Example card" status={READY} isEmpty emptyTitle="Nothing here">
        <p>hidden</p>
      </DashboardCard>
    );

    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
  });
});

describe("AttentionCard", () => {
  it("shows the count, links each row and the view-all targets", () => {
    render(<AttentionCard attention={ATTENTION} status={READY} />);

    const upcoming = screen.getByRole("heading", { name: "Upcoming interviews (7 days)" }).closest("section");
    expect(upcoming).not.toBeNull();
    expect(within(upcoming!).getByText("2")).toBeInTheDocument();
    expect(within(upcoming!).getByRole("link", { name: /Globex/ })).toHaveAttribute("href", "/interviews/int-1");

    const stalled = screen.getByRole("heading", { name: "Stalled applications" }).closest("section");
    expect(within(stalled!).getByRole("link", { name: /Staff Engineer/ })).toHaveAttribute(
      "href",
      "/applications/app-1"
    );
    expect(within(stalled!).getByText(`Stalled · ${formatDuration(21)}`)).toBeInTheDocument();

    const errors = screen.getByRole("heading", { name: "Automation issues" }).closest("section");
    expect(within(errors!).getByRole("link", { name: /feed returned 500/ })).toHaveAttribute("href", "/runs/run-f1");

    const viewAll = screen.getAllByRole("link", { name: /View all/ }).map((link) => link.getAttribute("href"));
    expect(viewAll).toEqual(["/interviews", "/applications?stalled=1", "/runs"]);
  });

  it("shows at most five rows per list while the count shows the full total", () => {
    const seven = Array.from({ length: 7 }, (_, index) => ({
      interviewId: `int-${index}`,
      applicationId: `app-${index}`,
      scheduledAt: FUTURE(index + 1),
      stage: "screening",
      company: `Company ${index}`,
    }));
    render(<AttentionCard attention={{ ...NO_ATTENTION, upcomingInterviews: seven }} status={READY} />);

    const upcoming = screen.getByRole("heading", { name: "Upcoming interviews (7 days)" }).closest("section");
    expect(within(upcoming!).getByText("7")).toBeInTheDocument();
    expect(within(upcoming!).getAllByRole("link", { name: /Company/ })).toHaveLength(5);
  });

  it("says when a failed run has no recorded time", () => {
    const untimed: AttentionBundle = {
      ...NO_ATTENTION,
      runErrors: [{ runId: "run-u1", at: null, provider: "Lever", summary: null }],
    };
    render(<AttentionCard attention={untimed} status={READY} />);

    const issues = screen.getByRole("heading", { name: "Automation issues" }).closest("section");
    expect(within(issues!).getByText("Failed")).toBeInTheDocument();
    expect(within(issues!).getByText("Run failed without a message")).toBeInTheDocument();
    expect(within(issues!).getByText("Time not recorded")).toBeInTheDocument();
  });

  it("uses a friendly empty text for each list", () => {
    render(<AttentionCard attention={NO_ATTENTION} status={READY} />);

    expect(screen.getByText("No interviews in the next 7 days.")).toBeInTheDocument();
    expect(screen.getByText("Nothing stalled. Nice.")).toBeInTheDocument();
    expect(screen.getByText("No failed automation runs in the last 7 days.")).toBeInTheDocument();
  });
});

describe("KpiRow", () => {
  it("shows Not enough data for rates with fewer than five applications and no tile for a missing rate", () => {
    render(
      <KpiRow kpis={EMPTY_KPIS} weeklyActivity={[]} status={READY} showDeltas />
    );

    expect(screen.getByText("Open pipeline")).toBeInTheDocument();
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    expect(screen.getByText("No applications in range")).toBeInTheDocument();
  });

  it("reports a rate with its sample size and a point change against the previous period", () => {
    render(<KpiRow kpis={KPIS} weeklyActivity={WEEKLY_ACTIVITY} status={READY} showDeltas />);

    expect(screen.getByText("44%")).toBeInTheDocument();
    expect(screen.getByText("· 41 apps")).toBeInTheDocument();
    expect(screen.getByText("−6 pts vs previous period")).toBeInTheDocument();
  });

  it("does not compare a rate whose previous sample is too small", () => {
    const small: DashboardKpis = {
      ...KPIS,
      responseRatePrev: { value: 0.5, n: 4 },
    };
    render(<KpiRow kpis={small} weeklyActivity={[]} status={READY} showDeltas />);

    expect(screen.getByText("Not enough data to compare")).toBeInTheDocument();
  });

  it("colours a change by whether it is good for the metric, and never by colour alone", () => {
    const { container } = render(<KpiRow kpis={KPIS} weeklyActivity={[]} status={READY} showDeltas />);
    const deltaFor = (text: string) => screen.getByText(text).closest("p");

    // Interviews fell from 3 to 1: a decrease is bad for this metric, and the text says so.
    expect(deltaFor("−2 vs previous period")).toHaveClass("text-danger");
    // Offers rose from 1 to 2: an increase is good.
    expect(deltaFor("+1 vs previous period")).toHaveClass("text-success");
    // Applications sent is a volume input, so a change has no good or bad colour.
    expect(deltaFor("+5 vs previous period")).toHaveClass("text-muted-foreground");
    expect(deltaFor("+5 vs previous period")).not.toHaveClass("text-success");
    // Open pipeline is flat here.
    expect(deltaFor("No change vs previous period")).toBeTruthy();
    expect(container.querySelectorAll("svg[aria-hidden='true']").length).toBeGreaterThan(0);
  });

  it("gives the trend sparklines an accessible summary", () => {
    render(<KpiRow kpis={KPIS} weeklyActivity={WEEKLY_ACTIVITY} status={READY} showDeltas />);

    expect(
      screen.getByRole("img", { name: /Applications per week: 4 in the first week, 2 in the latest week, peak 4/ })
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Interviews per week/ })).toBeInTheDocument();
  });

  it("explains that all-time ranges have no earlier period to compare", () => {
    render(<KpiRow kpis={KPIS} weeklyActivity={[]} status={READY} showDeltas={false} />);

    expect(screen.getAllByText("No earlier period to compare").length).toBeGreaterThan(0);
  });
});

describe("FunnelCard", () => {
  it("labels each cumulative step with its count and conversion", () => {
    render(<FunnelCard funnel={FUNNEL} status={READY} />);

    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("Final / onsite")).toBeInTheDocument();
    expect(screen.getByText("67% of applied (4 of 6)")).toBeInTheDocument();
    expect(screen.getByText("50% of screening (2 of 4)")).toBeInTheDocument();
    expect(screen.getByText("0% of final / onsite (0 of 1)")).toBeInTheDocument();
    expect(screen.getByText(/5 opportunities found, 4 evaluated, 6 applied/)).toBeInTheDocument();
  });

  it("shows an empty state when no applications were applied in range", () => {
    render(
      <FunnelCard
        funnel={{ ...FUNNEL, steps: FUNNEL.steps.map((step) => ({ ...step, count: 0, conversion: null })) }}
        status={READY}
      />
    );

    expect(screen.getByText("No applications in this range")).toBeInTheDocument();
  });
});

describe("SourceEffectivenessCard", () => {
  it("sorts sources by response rate and labels each bar with its sample", () => {
    render(<SourceEffectivenessCard sources={SOURCES} status={READY} />);

    const list = screen.getByRole("list", { name: "Response rate by source" });
    // Each row is a block whose first child holds the source name, then the rate label.
    const names = within(list)
      .getAllByRole("listitem")
      .map((item) => item.firstElementChild?.firstElementChild?.textContent);
    expect(names).toEqual(["Ashby", "Lever"]);
    expect(within(list).getByText("75% of 8 apps")).toBeInTheDocument();
    expect(within(list).getByText("40% of 5 apps")).toBeInTheDocument();
  });

  it("hides sources with fewer than three applications behind a show-all toggle", async () => {
    render(<SourceEffectivenessCard sources={SOURCES} status={READY} />);

    const list = screen.getByRole("list", { name: "Response rate by source" });
    expect(within(list).queryByText("Greenhouse")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Show all 3 sources" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);

    expect(within(list).getByText("Greenhouse")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show fewer sources" })).toHaveAttribute("aria-expanded", "true");
  });
});

describe("PipelineAgingCard", () => {
  it("says how many open applications there are, not how many rows it was given", () => {
    render(<PipelineAgingCard pipeline={PIPELINE} openCount={25} status={READY} />);

    expect(screen.getByText("Showing the 10 longest of 25 open applications.")).toBeInTheDocument();
  });

  it("shows no footer when every open application fits on the card", () => {
    render(<PipelineAgingCard pipeline={PIPELINE} openCount={PIPELINE.length} status={READY} />);

    expect(screen.queryByText(/Showing the 10 longest/)).not.toBeInTheDocument();
  });

  it("links each open application and labels its aging bucket in text", () => {
    render(<PipelineAgingCard pipeline={PIPELINE} status={READY} />);

    expect(screen.getByRole("link", { name: /Staff Engineer/ })).toHaveAttribute("href", "/applications/app-1");
    expect(screen.getByText("21 days")).toBeInTheDocument();
    expect(screen.getByText(/Globex · Screening · Stalled/)).toBeInTheDocument();
    expect(screen.getByText(/Initech · Onsite · Recent/)).toBeInTheDocument();
  });

  it("renders an empty state", () => {
    render(<PipelineAgingCard pipeline={[]} status={READY} />);

    expect(screen.getByText("No open applications")).toBeInTheDocument();
  });
});

describe("WeeklyActivityCard", () => {
  it("provides a visually hidden table with the same weekly numbers", () => {
    render(<WeeklyActivityCard weeklyActivity={WEEKLY_ACTIVITY} status={READY} />);

    const table = screen.getByRole("table", { name: /Weekly activity/ });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByRole("columnheader", { name: "Applied" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "3 Jun 2024" })).toBeInTheDocument();
  });

  it("renders an empty state when there is no activity", () => {
    render(<WeeklyActivityCard weeklyActivity={[]} status={READY} />);

    expect(screen.getByText("No activity in this range")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("RunHealthCard", () => {
  it("leaves runs that have not ended out of the finished count", () => {
    const running = { ...RUNS[0], id: "run-running", status: "running" };
    render(<RunHealthCard runs={[running, ...RUNS]} lastFailure={LAST_FAILURE} status={READY} />);

    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("shows the latest run, how many finished without errors, and the last failure", () => {
    render(<RunHealthCard runs={RUNS} lastFailure={LAST_FAILURE} status={READY} />);

    expect(screen.getByRole("link", { name: "2024-06-30-ashby" })).toHaveAttribute("href", "/runs/run-1");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "feed returned 500" })).toHaveAttribute("href", "/runs/run-2");
  });

  it("says the time is not recorded when the last failure has no time", () => {
    render(<RunHealthCard runs={RUNS} lastFailure={{ ...LAST_FAILURE, at: null }} status={READY} />);

    expect(screen.getByText("Time not recorded")).toBeInTheDocument();
  });

  it("renders an empty state with no runs", () => {
    render(<RunHealthCard runs={[]} lastFailure={null} status={READY} />);

    expect(screen.getByText("No automation runs yet")).toBeInTheDocument();
  });
});
