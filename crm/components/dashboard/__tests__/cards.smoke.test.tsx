import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FunnelCard } from "@/components/dashboard/funnel-card";
import { KpiRow } from "@/components/dashboard/kpi-row";
import { PipelineAgingCard } from "@/components/dashboard/pipeline-aging-card";
import { RunHealthCard } from "@/components/dashboard/run-health-card";
import { SourceEffectivenessCard } from "@/components/dashboard/source-effectiveness-card";
import { UpcomingCard } from "@/components/dashboard/upcoming-card";
import { VelocityCard } from "@/components/dashboard/velocity-card";
import type {
  DashboardKpis,
  FunnelSummary,
  PipelineAgingRow,
  SourceEffectiveness,
  UpcomingItem,
  WeeklyActivityPoint,
} from "@/lib/analytics";
import type { Tables } from "@/types/database.types";

const EMPTY_KPIS: DashboardKpis = {
  openApplications: 0,
  openApplicationsPrev: 0,
  appliedInRange: 0,
  appliedPrevPeriod: 0,
  responseRate: { value: null, n: 0 },
  responseRatePrev: { value: null, n: 0 },
  interviewsInRange: 0,
  interviewsPrev: 0,
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
  responseRate: { value: 0.44, n: 9 },
  responseRatePrev: { value: 0.5, n: 4 },
  interviewsInRange: 3,
  interviewsPrev: 3,
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

const FUNNEL: FunnelSummary = {
  steps: [
    { key: "opportunities", label: "Opportunities", count: 40, conversion: null },
    { key: "evaluated", label: "Evaluated", count: 24, conversion: { value: 0.6, n: 40 } },
    { key: "applied", label: "Applied", count: 12, conversion: { value: 0.5, n: 24 } },
    { key: "interviewing", label: "Interviewing", count: 4, conversion: { value: 0.33, n: 12 } },
    { key: "offers", label: "Offer", count: 1, conversion: { value: 0.25, n: 4 } },
  ],
};

const SOURCES: SourceEffectiveness[] = [
  {
    providerId: "p1",
    slug: "ashby",
    name: "Ashby",
    opportunities: 20,
    applications: 8,
    applicationsWithInterview: 4,
    offers: 1,
    appToInterview: { value: 0.5, n: 8 },
  },
  {
    providerId: "p2",
    slug: "lever",
    name: "Lever",
    opportunities: 12,
    applications: 0,
    applicationsWithInterview: 0,
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
    daysInStage: 21,
    appliedAt: "2024-06-01T09:00:00.000Z",
  },
  {
    applicationId: "app-2",
    company: "Initech",
    title: "Platform Lead",
    stage: "onsite",
    daysInStage: 3,
    appliedAt: "2024-06-18T09:00:00.000Z",
  },
];

const UPCOMING: UpcomingItem[] = [
  { at: "2024-07-01T14:30:00.000Z", label: "Interview (onsite)", href: "/interviews/int-1" },
  { at: "2024-07-03T09:00:00.000Z", label: "Follow-up call", href: "/applications/app-1" },
];

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

function makeRunEvent(
  overrides: Partial<Tables<"automation_run_events">>
): Tables<"automation_run_events"> {
  return {
    id: "event-1",
    provider_id: null,
    automation_run_id: null,
    run_key: null,
    event_type: "fetch",
    severity: "info",
    message: null,
    metadata: {},
    created_at: "2024-06-30T09:00:00.000Z",
    ...overrides,
  };
}

const RUNS: Tables<"automation_runs">[] = [
  makeRun({
    id: "run-1",
    run_key: "2024-06-30-ashby",
    status: "completed",
    source_items_count: 42,
    opportunities_count: 12,
    evaluations_count: 9,
  }),
  makeRun({ id: "run-2", run_key: "2024-06-29-lever", status: "failed" }),
];

const RUN_EVENTS: Tables<"automation_run_events">[] = [
  makeRunEvent({ id: "rev-1", severity: "info", message: "fetched 42 items" }),
  makeRunEvent({
    id: "rev-2",
    severity: "error",
    event_type: "parse",
    message: "feed returned 500",
  }),
];

describe("FunnelCard", () => {
  it("renders with no funnel row", () => {
    render(<FunnelCard funnel={null} />);

    expect(screen.getByText("Funnel")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(4);
  });

  it("renders each step conversion rate", () => {
    render(<FunnelCard funnel={FUNNEL} />);

    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("33%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
});

describe("KpiRow", () => {
  it("renders zeroed tiles with no activity", () => {
    render(<KpiRow kpis={EMPTY_KPIS} weeklyActivity={[]} />);

    expect(screen.getByText("Open applications")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    // Response rate and average score have no sample, so both show a dash.
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getAllByText("No change")).toHaveLength(6);
  });

  it("renders values and signed deltas", () => {
    render(<KpiRow kpis={KPIS} weeklyActivity={WEEKLY_ACTIVITY} />);

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("44%")).toBeInTheDocument();
    expect(screen.getByText("7.4")).toBeInTheDocument();
    expect(screen.getByText("+5")).toBeInTheDocument();
    expect(screen.getByText("-6")).toBeInTheDocument();
    // "Open applications" and "Interviews" are flat against the previous period.
    expect(screen.getAllByText("No change")).toHaveLength(2);
  });
});

describe("PipelineAgingCard", () => {
  it("renders an empty state", () => {
    render(<PipelineAgingCard pipeline={[]} />);

    expect(screen.getByText("No open applications")).toBeInTheDocument();
  });

  it("links each row and flags stale stages", () => {
    render(<PipelineAgingCard pipeline={PIPELINE} />);

    expect(screen.getByRole("link", { name: /Staff Engineer/ })).toHaveAttribute(
      "href",
      "/applications/app-1"
    );
    expect(screen.getByText(/Globex · screening/)).toBeInTheDocument();
    expect(screen.getByText(/Initech · onsite/)).toBeInTheDocument();
    expect(screen.getByText("21d")).toBeInTheDocument();
    expect(screen.getByText("3d")).toBeInTheDocument();
  });
});

describe("SourceEffectivenessCard", () => {
  it("renders an empty state when no provider has applications", () => {
    render(<SourceEffectivenessCard sources={[]} />);

    expect(screen.getByText("No application data yet")).toBeInTheDocument();
    render(<SourceEffectivenessCard sources={[SOURCES[1]]} />);
    expect(screen.getAllByText("No application data yet")).toHaveLength(2);
  });

  it("renders the chart once a provider has applications", () => {
    const { container } = render(<SourceEffectivenessCard sources={SOURCES} />);

    expect(screen.getByText("Source effectiveness")).toBeInTheDocument();
    expect(screen.queryByText("No application data yet")).not.toBeInTheDocument();
    expect(container.querySelector("[data-slot='chart']")).not.toBeNull();
  });
});

describe("UpcomingCard", () => {
  it("renders an empty state", () => {
    render(<UpcomingCard upcoming={[]} />);

    expect(screen.getByText("Nothing scheduled")).toBeInTheDocument();
  });

  it("renders each item as a link", () => {
    render(<UpcomingCard upcoming={UPCOMING} />);

    expect(screen.getByRole("link", { name: /Interview \(onsite\)/ })).toHaveAttribute(
      "href",
      "/interviews/int-1"
    );
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });
});

describe("VelocityCard", () => {
  it("renders an empty state", () => {
    render(<VelocityCard weeklyActivity={[]} />);

    expect(screen.getByText("No activity in selected range")).toBeInTheDocument();
  });

  it("renders the chart with weekly activity", () => {
    const { container } = render(<VelocityCard weeklyActivity={WEEKLY_ACTIVITY} />);

    expect(screen.getByText("Velocity")).toBeInTheDocument();
    expect(screen.queryByText("No activity in selected range")).not.toBeInTheDocument();
    expect(container.querySelector("[data-slot='chart']")).not.toBeNull();
  });
});

describe("RunHealthCard", () => {
  it("renders an empty state with a zero success rate", () => {
    render(<RunHealthCard runs={[]} runEvents={[]} />);

    expect(screen.getByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText(/0% success/)).toBeInTheDocument();
  });

  it("summarizes success rate, run links and recent errors", () => {
    render(<RunHealthCard runs={RUNS} runEvents={RUN_EVENTS} />);

    expect(screen.getByText(/50% success/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /2024-06-30-ashby/ })).toHaveAttribute(
      "href",
      "/runs/run-1"
    );
    expect(screen.getByText("src 42 · opp 12 · eval 9")).toBeInTheDocument();
    expect(screen.getByText("Recent errors")).toBeInTheDocument();
    expect(screen.getByText("feed returned 500")).toBeInTheDocument();
    expect(screen.queryByText("fetched 42 items")).not.toBeInTheDocument();
  });
});
