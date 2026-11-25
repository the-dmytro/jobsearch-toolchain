import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApplicationsTable } from "@/components/applications/applications-table";
import type { ApplicationWithJoins } from "@/components/applications/use-applications-query";

const row = {
  id: "app-1",
  opportunities: { title: "Platform Engineer", source_url: null },
  organizations: { name: "Acme" },
  status: "active",
  current_stage: "applied",
  applied_at: "2026-11-01",
} as unknown as ApplicationWithJoins;

describe("ApplicationsTable (TanStack v9)", () => {
  it("renders headers and one row per application", () => {
    render(<ApplicationsTable data={[row]} />);

    for (const header of ["Role", "Company", "Status", "Stage", "Applied"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Platform Engineer" })).toHaveAttribute(
      "href",
      "/applications/app-1"
    );
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("applied")).toBeInTheDocument();
  });

  it("shows the empty state when there is no data", () => {
    render(<ApplicationsTable data={[]} />);

    expect(screen.getByText("No applications")).toBeInTheDocument();
  });
});
