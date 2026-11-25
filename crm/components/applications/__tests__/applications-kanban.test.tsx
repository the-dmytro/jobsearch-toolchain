import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApplicationsKanban,
  describeDragCancel,
  describeDragEnd,
  describeDragOver,
  describeDragStart,
  stageForColumn,
} from "@/components/applications/applications-kanban";
import { decorateApplications, type ApplicationRow } from "@/components/applications/application-model";
import { useStageMove } from "@/components/applications/use-stage-move";
import type { ApplicationsBundle } from "@/components/applications/use-applications-query";
import { qk } from "@/lib/query-keys";

const actions = vi.hoisted(() => ({ changeApplicationStage: vi.fn() }));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));

vi.mock("@/lib/actions/applications", () => ({
  changeApplicationStage: actions.changeApplicationStage,
}));
vi.mock("sonner", () => ({ toast }));

function application(id: string, stage: string, company = "Acme", role = "Role") {
  return {
    id,
    opportunity_id: `opp-${id}`,
    organization_id: "org-1",
    provider_id: null,
    application_channel: null,
    status: "active",
    current_stage: stage,
    applied_at: "2026-11-01T09:00:00Z",
    salary_requested_text: null,
    salary_requested_min: null,
    salary_requested_max: null,
    salary_requested_currency: null,
    outcome: null,
    decline_reason: null,
    passed: null,
    notes: null,
    metadata: {},
    created_at: "2026-11-01T09:00:00Z",
    updated_at: "2026-11-02T09:00:00Z",
    opportunities: { title: role, source_url: null },
    organizations: { name: company },
  } as unknown as ApplicationsBundle["applications"][number];
}

const NOW = Date.parse("2026-11-25T12:00:00Z");

function bundleOf(applications: ApplicationsBundle["applications"]): ApplicationsBundle {
  return { applications, events: [], interviews: [], communications: [] };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeClient(seed: ApplicationsBundle) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(qk.applications, seed);
  return client;
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  actions.changeApplicationStage.mockReset();
  toast.error.mockReset();
});

describe("drag announcements", () => {
  const data = { label: "Acme, Platform Engineer", column: "applied" as const };

  it("describes pick-up in plain language with the keyboard steps", () => {
    expect(describeDragStart(data)).toBe(
      "Picked up Acme, Platform Engineer, in Applied. Use the arrow keys to choose a stage, then press space or enter to drop it. Press escape to cancel."
    );
  });

  it("says which stage the card is over, or that it is over none", () => {
    expect(describeDragOver(data, "onsite")).toBe("Acme, Platform Engineer is over Onsite.");
    expect(describeDragOver(data, null)).toBe("Acme, Platform Engineer is not over a stage.");
  });

  it("reports a drop, a drop onto the same stage, and a drop outside the board", () => {
    expect(describeDragEnd(data, "offer")).toBe(
      "Dropped Acme, Platform Engineer into Offer. Saving the new stage."
    );
    expect(describeDragEnd(data, "applied")).toBe("Acme, Platform Engineer stayed in Applied.");
    expect(describeDragEnd(data, null)).toBe(
      "Acme, Platform Engineer was dropped outside the board. Nothing changed."
    );
  });

  it("reports a cancelled move", () => {
    expect(describeDragCancel(data)).toBe("Move cancelled. Acme, Platform Engineer stays in Applied.");
  });

  it("writes the Closed column as a rejection, and other columns as their own stage", () => {
    expect(stageForColumn("closed")).toBe("rejected");
    expect(stageForColumn("tech_interview")).toBe("tech_interview");
  });
});

describe("useStageMove", () => {
  it("shows the new stage at once, then rolls back when the server refuses the move", async () => {
    const seed = bundleOf([application("app-1", "applied")]);
    const client = makeClient(seed);
    const pending = deferred<{ ok: boolean; message?: string }>();
    actions.changeApplicationStage.mockReturnValue(pending.promise);

    const { result } = renderHook(() => useStageMove(), { wrapper: wrapperFor(client) });

    act(() => {
      result.current.move("app-1", "screening");
    });

    // Optimistic: the cache already shows the new stage and the card is marked as saving.
    await waitFor(() =>
      expect(client.getQueryData<ApplicationsBundle>(qk.applications)?.applications[0].current_stage).toBe(
        "screening"
      )
    );
    expect(result.current.pendingIds.has("app-1")).toBe(true);
    expect(actions.changeApplicationStage).toHaveBeenCalledWith({
      applicationId: "app-1",
      newStage: "screening",
    });

    await act(async () => {
      pending.resolve({ ok: false, message: "Could not move the application. Try again." });
      await pending.promise.catch(() => undefined);
    });

    await waitFor(() =>
      expect(client.getQueryData<ApplicationsBundle>(qk.applications)?.applications[0].current_stage).toBe(
        "applied"
      )
    );
    expect(toast.error).toHaveBeenCalledWith("Could not move the application. Try again.");
    expect(result.current.pendingIds.size).toBe(0);
    expect(client.getQueryData<ApplicationsBundle>(qk.applications)?.events).toEqual([]);
  });

  it("uses a friendly message when the request itself fails", async () => {
    const client = makeClient(bundleOf([application("app-2", "applied")]));
    actions.changeApplicationStage.mockRejectedValue(new TypeError("Failed to fetch"));

    const { result } = renderHook(() => useStageMove(), { wrapper: wrapperFor(client) });
    act(() => {
      result.current.move("app-2", "offer");
    });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Couldn't reach the server. Check your connection and try again."
      )
    );
    expect(client.getQueryData<ApplicationsBundle>(qk.applications)?.applications[0].current_stage).toBe(
      "applied"
    );
  });

  it("keeps the optimistic stage when the server accepts the move", async () => {
    const client = makeClient(bundleOf([application("app-3", "applied")]));
    actions.changeApplicationStage.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useStageMove(), { wrapper: wrapperFor(client) });
    act(() => {
      result.current.move("app-3", "onsite");
    });

    await waitFor(() => expect(result.current.pendingIds.size).toBe(0));
    expect(toast.error).not.toHaveBeenCalled();
    expect(client.getQueryData<ApplicationsBundle>(qk.applications)?.applications[0].current_stage).toBe("onsite");
  });
});

describe("ApplicationsKanban", () => {
  function rowsFor(): ApplicationRow[] {
    return decorateApplications(
      bundleOf([
        application("app-1", "applied", "Acme", "Platform Engineer"),
        application("app-2", "offer", "Globex", "Data Engineer"),
        application("app-3", "Rejected after screen", "Initech", "SRE"),
      ]),
      NOW
    );
  }

  it("renders one labelled column per stage, with counts, and the Closed column for declines", () => {
    const client = makeClient(bundleOf([]));
    render(<ApplicationsKanban rows={rowsFor()} />, { wrapper: wrapperFor(client) });

    for (const heading of ["Applied", "Screening", "Tech interview", "Onsite", "Offer", "Closed"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    const closed = screen.getByRole("region", { name: "Closed" });
    expect(within(closed).getByText("SRE")).toBeInTheDocument();
    expect(within(closed).getByText("Rejected")).toBeInTheDocument();
  });

  it("gives each card a separate Move button, and keeps the role link on the card", () => {
    const client = makeClient(bundleOf([]));
    render(<ApplicationsKanban rows={rowsFor()} />, { wrapper: wrapperFor(client) });

    const handle = screen.getByRole("button", { name: "Move Acme Platform Engineer" });
    expect(handle.tagName).toBe("BUTTON");
    expect(screen.getByRole("link", { name: "Platform Engineer" })).toHaveAttribute(
      "href",
      "/applications/app-1"
    );
  });

  it("explains the keyboard drag steps to screen reader users", () => {
    const client = makeClient(bundleOf([]));
    render(<ApplicationsKanban rows={rowsFor()} />, { wrapper: wrapperFor(client) });

    expect(
      screen.getByText(/To move an application, press space or enter on its Move button/)
    ).toBeInTheDocument();
  });

  it("lays columns out as a horizontal snap strip on small screens", () => {
    const client = makeClient(bundleOf([]));
    const { container } = render(<ApplicationsKanban rows={rowsFor()} />, { wrapper: wrapperFor(client) });

    const strip = container.querySelector(".snap-x");
    expect(strip).not.toBeNull();
    expect(strip?.className).toContain("overflow-x-auto");
  });
});
