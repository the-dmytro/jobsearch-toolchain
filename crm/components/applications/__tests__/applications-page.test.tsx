import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicationsPage } from "@/components/applications/applications-page";
import type { ApplicationsBundle } from "@/components/applications/use-applications-query";

// A tiny in-memory router: `replace` updates the search string, and the mocked
// `useSearchParams` re-renders its subscribers, like Next's App Router does.
const nav = vi.hoisted(() => ({
  search: "",
  listeners: new Set<() => void>(),
  query: {
    data: undefined as ApplicationsBundle | undefined,
    isPending: true,
    isError: false,
    error: null as unknown,
    refetch: () => Promise.resolve(),
  },
}));

vi.mock("next/navigation", async () => {
  const React = await import("react");
  return {
    usePathname: () => "/applications",
    useRouter: () => ({
      replace: (href: string) => {
        const at = href.indexOf("?");
        nav.search = at === -1 ? "" : href.slice(at + 1);
        nav.listeners.forEach((listener) => listener());
      },
      push: () => {},
      refresh: () => {},
    }),
    useSearchParams: () => {
      const search = React.useSyncExternalStore(
        (listener: () => void) => {
          nav.listeners.add(listener);
          return () => nav.listeners.delete(listener);
        },
        () => nav.search
      );
      return React.useMemo(() => new URLSearchParams(search), [search]);
    },
  };
});

vi.mock("@/components/applications/use-applications-query", () => ({
  useApplicationsQuery: () => nav.query,
}));

const STAGES = ["Applied", "Phone screen", "Technical interview", "Final interview loop", "Offer meeting", "Rejected"];
const COMPANIES = [
  { id: "org-acme", name: "Acme" },
  { id: "org-globex", name: "Globex" },
  { id: "org-initech", name: "Initech" },
];

function makeBundle(count: number): ApplicationsBundle {
  const applications = Array.from({ length: count }, (_, i) => {
    const company = COMPANIES[i % 3];
    const number = String(i + 1).padStart(2, "0");
    return {
      id: `app-${number}`,
      opportunity_id: `opp-${number}`,
      organization_id: company.id,
      provider_id: null,
      application_channel: null,
      status: "active",
      current_stage: STAGES[i % STAGES.length],
      applied_at: "2026-10-05T09:00:00Z",
      salary_requested_text: null,
      salary_requested_min: null,
      salary_requested_max: null,
      salary_requested_currency: null,
      outcome: null,
      decline_reason: null,
      passed: null,
      notes: i === 0 ? "Kubernetes platform" : null,
      metadata: {},
      created_at: "2026-10-04T09:00:00Z",
      // Later rows are updated later, so the default "Updated, newest first" order is clear.
      updated_at: new Date(Date.UTC(2026, 10, 1) + i * 3_600_000).toISOString(),
      opportunities: { title: `Role ${number}`, source_url: null },
      organizations: { name: company.name },
    } as unknown as ApplicationsBundle["applications"][number];
  });
  return { applications, events: [], interviews: [], communications: [] };
}

function setQuery(partial: Partial<typeof nav.query>) {
  nav.query = { ...nav.query, isPending: false, isError: false, error: null, ...partial };
}

function roleLinks() {
  return screen
    .getAllByRole("link")
    .filter((link) => link.getAttribute("href")?.startsWith("/applications/app-"));
}

beforeEach(() => {
  nav.search = "";
  nav.query = {
    data: makeBundle(30),
    isPending: false,
    isError: false,
    error: null,
    refetch: () => Promise.resolve(),
  };
});

describe("ApplicationsPage: table", () => {
  it("shows the first 25 rows, the result count and the page range", async () => {
    render(<ApplicationsPage />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(roleLinks()).toHaveLength(25);
    expect(screen.getByText("1–25 of 30")).toBeInTheDocument();
    expect(screen.getByText("30 applications")).toBeInTheDocument();
  });

  it("puts the role link in the first cell and keeps it keyboard reachable", async () => {
    render(<ApplicationsPage />);
    const firstRow = (await screen.findAllByRole("row"))[1];
    const link = within(firstRow).getByRole("link", { name: "Role 30" });
    expect(link).toHaveAttribute("href", "/applications/app-30");
    expect(firstRow.querySelector("td")).toContainElement(link);
  });

  it("filters by search text and writes the query to the URL", async () => {
    const user = userEvent.setup();
    render(<ApplicationsPage />);
    await screen.findByRole("table");

    await user.type(screen.getByRole("searchbox", { name: "Search" }), "globex");

    await waitFor(() => expect(nav.search).toContain("q=globex"));
    expect(screen.getByText("10 of 30 applications")).toBeInTheDocument();
    expect(roleLinks()).toHaveLength(10);
  });

  it("filters by stage, with aria-pressed on the toggle", async () => {
    const user = userEvent.setup();
    render(<ApplicationsPage />);
    await screen.findByRole("table");

    const stageGroup = screen.getByRole("group", { name: "Stage" });
    const offer = within(stageGroup).getByRole("button", { name: "Offer" });
    expect(offer).toHaveAttribute("aria-pressed", "false");

    await user.click(offer);

    expect(offer).toHaveAttribute("aria-pressed", "true");
    expect(nav.search).toContain("stage=offer");
    expect(screen.getByText("5 of 30 applications")).toBeInTheDocument();
  });

  it("sorts with aria-sort and reverses on a second click", async () => {
    const user = userEvent.setup();
    render(<ApplicationsPage />);
    await screen.findByRole("table");

    const companyHeader = screen.getByRole("columnheader", { name: "Company" });
    expect(companyHeader).toHaveAttribute("aria-sort", "none");

    await user.click(within(companyHeader).getByRole("button", { name: "Company" }));
    expect(companyHeader).toHaveAttribute("aria-sort", "ascending");
    // Acme comes first; ties keep the order the rows arrived in.
    expect(roleLinks()[0]).toHaveTextContent("Role 01");

    await user.click(within(companyHeader).getByRole("button", { name: "Company" }));
    expect(companyHeader).toHaveAttribute("aria-sort", "descending");
    expect(nav.search).toContain("sort=company");
  });

  it("pages through results and keeps the page in the URL", async () => {
    const user = userEvent.setup();
    render(<ApplicationsPage />);
    await screen.findByRole("table");

    const pages = screen.getByRole("navigation", { name: "Applications pages" });
    await user.click(within(pages).getByRole("button", { name: "Next" }));

    expect(screen.getByText("26–30 of 30")).toBeInTheDocument();
    expect(roleLinks()).toHaveLength(5);
    expect(nav.search).toContain("page=2");
  });

  it("can show 50 rows per page", async () => {
    const user = userEvent.setup();
    render(<ApplicationsPage />);
    await screen.findByRole("table");

    await user.selectOptions(screen.getByLabelText("Rows per page"), "50");

    expect(screen.getByText("1–30 of 30")).toBeInTheDocument();
    expect(nav.search).toContain("size=50");
  });
});

describe("ApplicationsPage: URL parameters", () => {
  it("reads filters, sort and page from the URL on first render", async () => {
    nav.search = "stalled=1&sort=company&dir=asc&page=1";
    render(<ApplicationsPage />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Stalled over 14 days/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("columnheader", { name: "Company" })).toHaveAttribute("aria-sort", "ascending");
  });

  it("ignores a malformed page number and falls back to page 1", async () => {
    nav.search = "page=banana&size=999";
    render(<ApplicationsPage />);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByText("1–25 of 30")).toBeInTheDocument();
  });

  it("clears every filter from the Clear filters button", async () => {
    const user = userEvent.setup();
    nav.search = "q=acme&stage=applied";
    render(<ApplicationsPage />);
    await screen.findByRole("table");

    await user.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(nav.search).toBe("");
    expect(screen.getByRole("searchbox", { name: "Search" })).toHaveValue("");
    expect(screen.getByText("30 applications")).toBeInTheDocument();
  });
});

describe("ApplicationsPage: states", () => {
  it("shows a loading skeleton while the first load is pending", () => {
    setQuery({ data: undefined, isPending: true });
    render(<ApplicationsPage />);

    expect(screen.getByRole("status", { name: "Loading applications" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows an empty state with a next step when there are no applications", async () => {
    setQuery({ data: { applications: [], events: [], interviews: [], communications: [] }, isPending: false });
    render(<ApplicationsPage />);

    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a friendly error with a retry when the list fails to load", () => {
    setQuery({
      data: undefined,
      isPending: false,
      isError: true,
      error: { code: "XX000", message: "relation applications does not exist" },
    });
    render(<ApplicationsPage />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Applications couldn't load");
    expect(alert).toHaveTextContent("Something went wrong. Please try again.");
    expect(alert.textContent).not.toContain("relation");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
