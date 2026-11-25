import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicationEditSheet } from "@/components/applications/application-edit-sheet";
import type { Tables } from "@/types/database.types";

const actions = vi.hoisted(() => ({
  updateApplication: vi.fn(),
  changeApplicationStage: vi.fn(),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("@/lib/actions/applications", () => ({
  updateApplication: actions.updateApplication,
  changeApplicationStage: actions.changeApplicationStage,
}));
vi.mock("sonner", () => ({ toast }));

// The Radix select is replaced by a native select, so a stage change can be driven in jsdom.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  return {
    Select: ({
      value,
      onValueChange,
      disabled,
      children,
    }: {
      value?: string;
      onValueChange: (v: string) => void;
      disabled?: boolean;
      children: ReactNode;
    }) =>
      React.createElement(
        "select",
        {
          "aria-label": "Stage",
          value,
          disabled,
          onChange: (event: { target: { value: string } }) => onValueChange(event.target.value),
        },
        children
      ),
    SelectTrigger: () => null,
    SelectValue: () => null,
    SelectContent: ({ children }: { children: ReactNode }) => children,
    SelectItem: ({ value, children }: { value: string; children: ReactNode }) =>
      React.createElement("option", { value }, children),
  };
});

const APP_ID = "11111111-1111-4111-8111-111111111111";

function application(overrides: Partial<Tables<"applications">> = {}): Tables<"applications"> {
  return {
    id: APP_ID,
    opportunity_id: "opp-1",
    organization_id: "org-1",
    provider_id: null,
    application_channel: null,
    status: "interviewing",
    current_stage: "screening",
    applied_at: "2026-10-05",
    salary_requested_text: "80k",
    salary_requested_min: null,
    salary_requested_max: null,
    salary_requested_currency: null,
    outcome: null,
    decline_reason: null,
    passed: null,
    notes: "Old notes",
    metadata: {},
    created_at: "2026-10-04T09:00:00Z",
    updated_at: "2026-10-05T09:00:00Z",
    ...overrides,
  } as unknown as Tables<"applications">;
}

function renderSheet(app: Tables<"applications">, onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ApplicationEditSheet application={app} open onOpenChange={onOpenChange} />
    </QueryClientProvider>
  );
  return { onOpenChange };
}

beforeEach(() => {
  actions.updateApplication.mockReset();
  actions.changeApplicationStage.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
});

describe("ApplicationEditSheet", () => {
  it("sends only the fields the user changed", async () => {
    actions.updateApplication.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    const { onOpenChange } = renderSheet(application());

    await screen.findByRole("dialog");
    const notes = () => screen.getByLabelText("Notes");
    await user.clear(notes());
    await user.type(notes(), "New notes");
    await waitFor(() => expect(notes()).toHaveValue("New notes"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(actions.updateApplication).toHaveBeenCalledTimes(1));
    const payload = actions.updateApplication.mock.calls[0][0];
    expect(Object.keys(payload).sort()).toEqual(["id", "notes"]);
    expect(payload).toEqual({ id: APP_ID, notes: "New notes" });
    expect(actions.changeApplicationStage).not.toHaveBeenCalled();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("sends an emptied text field as null", async () => {
    actions.updateApplication.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    renderSheet(application());

    const salary = screen.getByLabelText("Salary requested");
    await user.clear(salary);
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(actions.updateApplication).toHaveBeenCalledTimes(1));
    expect(actions.updateApplication.mock.calls[0][0]).toEqual({ id: APP_ID, salary_requested_text: null });
  });

  it("sends no update when nothing was changed", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderSheet(application());

    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(actions.updateApplication).not.toHaveBeenCalled();
  });

  it("moves the stage through changeApplicationStage and not the field update", async () => {
    actions.changeApplicationStage.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    renderSheet(application({ current_stage: "screening" }));

    await user.selectOptions(screen.getByLabelText("Stage"), "onsite");

    await waitFor(() =>
      expect(actions.changeApplicationStage).toHaveBeenCalledWith({ applicationId: APP_ID, newStage: "onsite" })
    );
    expect(actions.updateApplication).not.toHaveBeenCalled();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Stage updated"));
  });

  it("shows the friendly changed-elsewhere message when the stage was moved by someone else", async () => {
    const message = "This application changed elsewhere. Refresh and try again.";
    actions.changeApplicationStage.mockResolvedValue({ ok: false, message });
    const user = userEvent.setup();
    renderSheet(application({ current_stage: "screening" }));

    await user.selectOptions(screen.getByLabelText("Stage"), "onsite");

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(message));
  });

  it("shows status and outcome as read-only, not as inputs", () => {
    renderSheet(application({ outcome: "rejected", status: "rejected" }));

    expect(screen.queryByLabelText("Status")).toBeNull();
    expect(screen.queryByLabelText("Outcome")).toBeNull();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });
});

describe("ApplicationEditSheet typing safety", () => {
  it("keeps typed text when the parent re-renders with an equal record", async () => {
    actions.updateApplication.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const tree = (app: Tables<"applications">) => (
      <QueryClientProvider client={client}>
        <ApplicationEditSheet application={app} open onOpenChange={vi.fn()} />
      </QueryClientProvider>
    );
    const { rerender } = render(tree(application()));
    await screen.findByRole("dialog");
    const notes = () => screen.getByLabelText("Notes");
    await user.clear(notes());
    await user.type(notes(), "Draft");
    await waitFor(() => expect(notes()).toHaveValue("Draft"));
    rerender(tree(application()));
    await user.type(notes(), " text");
    await waitFor(() => expect(notes()).toHaveValue("Draft text"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(actions.updateApplication).toHaveBeenCalledTimes(1));
    expect(actions.updateApplication.mock.calls[0][0]).toEqual({ id: APP_ID, notes: "Draft text" });
  });
});
