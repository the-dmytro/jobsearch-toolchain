import { describe, expect, it } from "vitest";

import {
  applyStageChange,
  buildListSearchParams,
  companyOptions,
  decorateApplications,
  filterApplications,
  parseListState,
  revertStageChange,
  SORT_LABELS,
  type ListFilters,
} from "@/components/applications/application-model";
import type { ApplicationsBundle } from "@/components/applications/use-applications-query";
import { isStalled, lastActivityMs, latestActivityByApplication, STALLED_DAYS } from "@/lib/activity";

const DAY = 24 * 60 * 60 * 1000;
const NOW = Date.parse("2026-11-25T12:00:00Z");

function app(overrides: Record<string, unknown> = {}) {
  return {
    id: "app-1",
    opportunity_id: "opp-1",
    organization_id: "org-1",
    provider_id: null,
    application_channel: null,
    status: "applied",
    current_stage: "Applied",
    applied_at: "2026-11-20",
    salary_requested_text: null,
    salary_requested_min: null,
    salary_requested_max: null,
    salary_requested_currency: null,
    outcome: null,
    decline_reason: null,
    passed: null,
    notes: "Platform team, Kubernetes",
    metadata: {},
    created_at: "2026-11-19T09:00:00Z",
    updated_at: "2026-11-24T09:00:00Z",
    opportunities: { title: "Platform Engineer", source_url: null },
    organizations: { name: "Acme" },
    ...overrides,
  } as unknown as ApplicationsBundle["applications"][number];
}

function bundle(
  applications: ApplicationsBundle["applications"],
  events: ApplicationsBundle["events"] = [],
  extra: Partial<Pick<ApplicationsBundle, "interviews" | "communications">> = {}
): ApplicationsBundle {
  return { applications, events, interviews: [], communications: [], ...extra };
}

const NO_FILTERS: ListFilters = { q: "", stages: [], outcome: null, company: null, stalled: false };

describe("parseListState", () => {
  it("falls back to defaults for an empty or malformed URL", () => {
    const state = parseListState(new URLSearchParams("sort=bogus&page=-3&size=7&view=map&stage=nope"));
    expect(state).toMatchObject({
      q: "",
      stages: [],
      outcome: null,
      company: null,
      stalled: false,
      sort: "updated",
      desc: true,
      page: 1,
      pageSize: 25,
      view: "table",
    });
  });

  it("reads filters, stages, sort, paging and view from the URL", () => {
    const state = parseListState(
      new URLSearchParams(
        "q=acme&stage=offer&stage=applied&stage=offer&outcome=ghosted&company=org-9&stalled=1&sort=company&dir=asc&page=3&size=50&view=board"
      )
    );
    expect(state.q).toBe("acme");
    expect(state.stages).toEqual(["offer", "applied"]);
    expect(state.outcome).toBe("ghosted");
    expect(state.company).toBe("org-9");
    expect(state.stalled).toBe(true);
    expect(state.sort).toBe("company");
    expect(state.desc).toBe(false);
    expect(state.page).toBe(3);
    expect(state.pageSize).toBe(50);
    expect(state.view).toBe("board");
  });

  it("reads the stalled link from the attention card and maps the old declined outcome to rejected", () => {
    expect(parseListState(new URLSearchParams("stalled=1")).stalled).toBe(true);
    expect(parseListState(new URLSearchParams("outcome=declined")).outcome).toBe("rejected");
    expect(parseListState(new URLSearchParams("outcome=rejected")).outcome).toBe("rejected");
  });

  it("round-trips through buildListSearchParams and writes only non-default values", () => {
    const state = parseListState(new URLSearchParams("q=acme&stage=offer&stalled=1&page=2"));
    const out = buildListSearchParams(state).toString();
    expect(out).toBe("q=acme&stage=offer&stalled=1&page=2");
    expect(buildListSearchParams(parseListState(new URLSearchParams(""))).toString()).toBe("");
  });

  it("labels the days column as last activity", () => {
    expect(SORT_LABELS.days).toBe("Last activity");
  });
});

describe("decorateApplications: last activity", () => {
  it("counts days from the latest event, not from applying", () => {
    const rows = decorateApplications(
      bundle(
        [app()],
        [
          {
            id: "e1",
            application_id: "app-1",
            event_type: "stage_change",
            event_at: new Date(NOW - 3 * DAY).toISOString(),
            created_at: new Date(NOW - 3 * DAY).toISOString(),
            title: "Stage → screening",
            metadata: {},
          },
        ]
      ),
      NOW
    );
    expect(rows[0].daysSinceActivity).toBe(3);
  });

  it("counts an interview or a message as activity", () => {
    const rows = decorateApplications(
      bundle([app({ applied_at: "2026-10-01" })], [], {
        interviews: [{ id: "i1", application_id: "app-1", scheduled_at: new Date(NOW - 2 * DAY).toISOString(), result: null }],
        communications: [
          { id: "c1", application_id: "app-1", direction: "inbound", sent_at: new Date(NOW - 5 * DAY).toISOString(), created_at: new Date(NOW - 5 * DAY).toISOString() },
        ],
      }),
      NOW
    );
    expect(rows[0].daysSinceActivity).toBe(2);
  });

  it("ignores activity in the future", () => {
    const rows = decorateApplications(
      bundle([app({ applied_at: "2026-11-20" })], [], {
        interviews: [{ id: "i1", application_id: "app-1", scheduled_at: new Date(NOW + 3 * DAY).toISOString(), result: null }],
      }),
      NOW
    );
    expect(rows[0].daysSinceActivity).toBe(5);
  });

  it("falls back to applied_at, then created_at, when there is no other activity", () => {
    const [row] = decorateApplications(bundle([app({ applied_at: null })]), NOW);
    // created_at is 2026-11-19T09:00Z, six days and three hours before NOW.
    expect(row.daysSinceActivity).toBe(6);
  });

  it("marks an open application stalled after 14 days and never a closed one", () => {
    const old = new Date(NOW - 20 * DAY).toISOString();
    const rows = decorateApplications(
      bundle([
        app({ id: "open", applied_at: old, created_at: old }),
        app({ id: "rejected", applied_at: old, created_at: old, current_stage: "Rejected", status: "rejected", outcome: "rejected" }),
      ]),
      NOW
    );
    expect(rows.find((r) => r.id === "open")?.stalled).toBe(true);
    expect(rows.find((r) => r.id === "rejected")?.stalled).toBe(false);
    expect(rows.find((r) => r.id === "rejected")?.column).toBe("closed");
  });

  it("uses the role and company names from the joins", () => {
    const [row] = decorateApplications(bundle([app()]), NOW);
    expect(row).toMatchObject({ role: "Platform Engineer", company: "Acme", column: "applied" });
  });

  it("uses the same activity and stalled rule as the dashboard", () => {
    const old = new Date(NOW - 20 * DAY).toISOString();
    const input = bundle([app({ applied_at: old })]);
    const [row] = decorateApplications(input, NOW);
    const latest = latestActivityByApplication(input, NOW);
    const days = Math.floor((NOW - (lastActivityMs(input.applications[0], latest, NOW) ?? NOW)) / DAY);

    expect(row.daysSinceActivity).toBe(days);
    expect(row.stalled).toBe(isStalled(true, days));
    expect(STALLED_DAYS).toBe(14);
  });
});

describe("filterApplications", () => {
  const rows = decorateApplications(
    bundle([
      app({ id: "a", notes: "Kubernetes and Go" }),
      app({
        id: "b",
        organization_id: "org-2",
        notes: null,
        organizations: { name: "Globex" },
        opportunities: { title: "Data Engineer", source_url: null },
        current_stage: "Offer meeting",
        applied_at: new Date(NOW - 30 * DAY).toISOString(),
        created_at: new Date(NOW - 30 * DAY).toISOString(),
      }),
      app({ id: "c", current_stage: "Rejected", status: "rejected", outcome: "rejected", notes: null }),
    ]),
    NOW
  );

  it("searches company, role and notes, ignoring case", () => {
    expect(filterApplications(rows, { ...NO_FILTERS, q: "KUBERNETES" }).map((r) => r.id)).toEqual(["a"]);
    expect(filterApplications(rows, { ...NO_FILTERS, q: "globex" }).map((r) => r.id)).toEqual(["b"]);
    expect(filterApplications(rows, { ...NO_FILTERS, q: "data eng" }).map((r) => r.id)).toEqual(["b"]);
  });

  it("filters by stage column, with every closing outcome under Closed", () => {
    expect(filterApplications(rows, { ...NO_FILTERS, stages: ["closed"] }).map((r) => r.id)).toEqual(["c"]);
    expect(filterApplications(rows, { ...NO_FILTERS, stages: ["offer", "applied"] }).map((r) => r.id)).toEqual([
      "a",
      "b",
    ]);
  });

  it("filters by outcome and company, and by the stalled flag", () => {
    expect(filterApplications(rows, { ...NO_FILTERS, outcome: "rejected" }).map((r) => r.id)).toEqual(["c"]);
    expect(filterApplications(rows, { ...NO_FILTERS, company: "org-2" }).map((r) => r.id)).toEqual(["b"]);
    expect(filterApplications(rows, { ...NO_FILTERS, stalled: true }).map((r) => r.id)).toEqual(["b"]);
  });

  it("lists each company once, sorted by name", () => {
    expect(companyOptions(rows)).toEqual([
      { id: "org-1", name: "Acme" },
      { id: "org-2", name: "Globex" },
    ]);
  });
});

describe("optimistic stage helpers", () => {
  const base = bundle([app({ current_stage: "Applied" })], []);

  it("applies the new stage with the status and outcome the server writes, and adds a stage-change event", () => {
    const next = applyStageChange(base, "app-1", "screening", "optimistic-1", "2026-11-25T12:00:00Z");
    expect(next.applications[0]).toMatchObject({ current_stage: "screening", status: "interviewing", outcome: null });
    expect(next.events).toHaveLength(1);
    expect(next.events[0]).toMatchObject({ id: "optimistic-1", event_type: "stage_change" });
  });

  it("moves an application out of Closed by clearing its rejection at once", () => {
    const closed = bundle([app({ current_stage: "Rejected", status: "rejected", outcome: "rejected" })]);
    const next = applyStageChange(closed, "app-1", "tech_interview", "optimistic-2", "2026-11-25T12:00:00Z");
    const [row] = decorateApplications(next, NOW);
    expect(row).toMatchObject({ column: "tech_interview", outcome: "active" });
  });

  it("reverts the stage fields it read and removes the optimistic event", () => {
    const previous = { current_stage: "Rejected", status: "rejected", outcome: "rejected" };
    const moved = applyStageChange(base, "app-1", "screening", "optimistic-1", "2026-11-25T12:00:00Z");
    const reverted = revertStageChange(moved, "app-1", previous, "optimistic-1");
    expect(reverted.applications[0]).toMatchObject(previous);
    expect(reverted.events).toEqual([]);
  });
});
