import { describe, expect, it } from "vitest";
import { routeUsesDateRange } from "@/lib/date-range-routes";

describe("routeUsesDateRange", () => {
  it("is true for the dashboard and insights, the pages that read the range", () => {
    expect(routeUsesDateRange("/")).toBe(true);
    expect(routeUsesDateRange("/insights")).toBe(true);
  });

  it("is false for every other page", () => {
    for (const path of ["/applications", "/opportunities", "/runs", "/runs/abc", "/insights/extra", "/settings", "/interviews"]) {
      expect(routeUsesDateRange(path)).toBe(false);
    }
  });
});
