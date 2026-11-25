import { describe, expect, it } from "vitest";
import { breadcrumbSegments } from "@/components/crm/dashboard-shell";

describe("breadcrumbSegments", () => {
  it("labels a record page under a section as Details", () => {
    expect(breadcrumbSegments("/runs/4fe9666c-e389-4b96-9f98-298d69bcf6da")).toEqual([
      { href: "/runs", label: "Automation runs" },
      { href: "/runs/4fe9666c-e389-4b96-9f98-298d69bcf6da", label: "Details" },
    ]);
  });

  it("keeps section and dashboard labels", () => {
    expect(breadcrumbSegments("/")).toEqual([{ href: "/", label: "Dashboard" }]);
    expect(breadcrumbSegments("/insights")).toEqual([{ href: "/insights", label: "Insights" }]);
  });
});
