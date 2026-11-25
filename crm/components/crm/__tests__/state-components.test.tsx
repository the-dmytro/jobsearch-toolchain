import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CardSkeleton } from "@/components/crm/card-skeleton";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { Stat } from "@/components/crm/stat";
import { TableSkeleton } from "@/components/crm/table-skeleton";

describe("ErrorState", () => {
  it("announces the failure with role=alert and a friendly message", () => {
    render(<ErrorState title="Applications failed to load" error={new TypeError("Failed to fetch")} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Applications failed to load");
    expect(alert).toHaveTextContent(/couldn't reach the server/i);
  });

  it("never prints raw JSON or database internals", () => {
    const raw = { code: "XX000", message: "boom", details: { table: "applications" } };
    const { container } = render(<ErrorState error={raw} />);
    expect(container.textContent).not.toMatch(/[{}]/);
    expect(container.textContent).not.toContain("applications");
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
  });

  it("maps a permission denial to a permission message", () => {
    render(<ErrorState error={{ code: "42501", message: "permission denied for table x" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/don't have permission/i);
  });

  it("calls onRetry when Try again is pressed", () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new Error("x")} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("omits the retry button when no handler is given", () => {
    render(<ErrorState error={new Error("x")} />);
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("uses a fixed description when one is provided", () => {
    render(<ErrorState error={new Error("hidden")} description="Insights are unavailable." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Insights are unavailable.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("hidden");
  });
});

describe("loading skeletons", () => {
  it("TableSkeleton is a polite status region with an accessible name", () => {
    render(<TableSkeleton rows={3} cols={2} label="Loading applications" />);
    const region = screen.getByRole("status", { name: "Loading applications" });
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Loading applications…")).toBeInTheDocument();
  });

  it("TableSkeleton clamps invalid row and column counts", () => {
    const { container } = render(<TableSkeleton rows={0} cols={-4} />);
    const body = container.querySelectorAll('[aria-hidden="true"] > .grid');
    expect(body.length).toBe(1);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("CardSkeleton is a polite status region", () => {
    render(<CardSkeleton lines={4} label="Loading pipeline" />);
    expect(screen.getByRole("status", { name: "Loading pipeline" })).toHaveAttribute(
      "aria-live",
      "polite"
    );
  });
});

describe("EmptyState", () => {
  it("renders the title, description and action", () => {
    render(
      <EmptyState
        title="No applications yet"
        description="Add one to start tracking."
        action={<button type="button">Add application</button>}
      />
    );
    expect(screen.getByRole("heading", { name: "No applications yet" })).toBeInTheDocument();
    expect(screen.getByText("Add one to start tracking.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add application" })).toBeInTheDocument();
  });

  it("hides the decorative icon from assistive technology", () => {
    const { container } = render(<EmptyState title="Nothing" icon={<svg data-testid="icon" />} />);
    const wrapper = container.querySelector('[aria-hidden="true"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper?.querySelector('[data-testid="icon"]')).not.toBeNull();
  });
});

describe("Stat", () => {
  it("pairs the label with the value in a description list", () => {
    render(<Stat label="Interviews" value="7" sub="3 scheduled" />);
    expect(screen.getByText("Interviews").tagName).toBe("SPAN");
    expect(screen.getByText("Interviews").closest("dt")).not.toBeNull();
    expect(screen.getByText("7").closest("dd")).toHaveClass("tabular-nums");
    expect(screen.getByText("3 scheduled")).toBeInTheDocument();
  });

  it("turns tabular figures off when asked", () => {
    render(<Stat label="Hero" value="42" tabular={false} />);
    expect(screen.getByText("42")).not.toHaveClass("tabular-nums");
  });
});

describe("PageHeader", () => {
  it("renders one h1 with the title, formatted count and actions", () => {
    render(
      <PageHeader
        title="Applications"
        count={12480}
        description="Every role you track."
        actions={<button type="button">Add</button>}
      />
    );
    expect(screen.getByRole("heading", { level: 1, name: "Applications" })).toBeInTheDocument();
    expect(screen.getByText("12,480")).toBeInTheDocument();
    expect(screen.getByText("Every role you track.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("omits the count badge when no count is given", () => {
    const { container } = render(<PageHeader title="Companies" />);
    expect(container.querySelectorAll('[data-slot="badge"]').length).toBe(0);
  });
});
