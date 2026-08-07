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
  PipelineAging,
  SourceEffectiveness,
  UpcomingItem,
  WeeklyActivity,
} from "@/lib/analytics";
import type { Tables } from "@/types/database.types";

const EMPTY_KPIS: DashboardKpis = {
  openApplications: 0,
  appliedInRange: 0,
  appliedPrevPeriod: 0,
  responseRate: 0,
  responseRatePrev: 0,
  interviewsInRange: 0,
  interviewsPrev: 0,
  newOpportunities: 0,
  newOpportunitiesPrev: 0,
  avgScore: 0,
  avgScorePrev: 0,
};

const KPIS: DashboardKpis = {
  openApplications: 12,
  appliedInRange: 9,
  appliedPrevPeriod: 4,
  responseRate: 44,
  responseRatePrev: 50,
  interviewsInRange: 3,
  interviewsPrev: 3,
  newOpportunities: 17,
  newOpportunitiesPrev: 11,
  avgScore: 7.4,
  avgScorePrev: 6.9,
};

const WEEKLY_ACTIVITY: WeeklyActivity[] = [
  { week_start: "2024-06-03", opportunities: 8, applications: 4, interviews: 1 },
  { week_start: "2024-06-10", opportunities: 5, applications: 3, interviews: 2 },
  { week_start: "2024-06-17", opportunities: 4, applications: 2, interviews: 0 },
];

const FUNNEL: FunnelSummary = {
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

const SOURCES: SourceEffectiveness[] = [
  {
    provider_id: "p1",
    provider_slug: "ashby",
    provider_name: "Ashby",
    opportunities: 20,
    applications: 8,
    interviews: 4,
    offers: 1,
    app_to_interview_pct: 50,
  },
  {
    provider_id: "p2",
    provider_slug: "lever",
    provider_name: "Lever",
    opportunities: 12,
    applications: 0,
    interviews: 0,
    offers: 0,
    app_to_interview_pct: 0,
  },
];

const PIPELINE: PipelineAging[] = [
  {
    application_id: "app-1",
    organization_name: "Globex",
    opportunity_title: "Staff Engineer",
    current_stage: "phone",
    status: "active",
    days_in_stage: 21,
    applied_at: "2024-06-01T09:00:00.000Z",
    updated_at: "2024-06-02T09:00:00.000Z",
  },
  {
    application_id: "app-2",
    organization_name: "Initech",
    opportunity_title: "Platform Lead",
    current_stage: "final",
    status: "active",
    days_in_stage: 3,
    applied_at: "2024-06-18T09:00:00.000Z",
    updated_at: "2024-06-19T09:00:00.000Z",
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
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getAllByText("No change")).toHaveLength(6);
  });

  it("renders values and signed deltas", () => {
    render(<KpiRow kpis={KPIS} weeklyActivity={WEEKLY_ACTIVITY} />);

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("44%")).toBeInTheDocument();
    expect(screen.getByText("7.4")).toBeInTheDocument();
    expect(screen.getByText("+5")).toBeInTheDocument();
    expect(screen.getByText("-6")).toBeInTheDocument();
    // "Open applications" has no comparison period, "Interviews" is flat.
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
