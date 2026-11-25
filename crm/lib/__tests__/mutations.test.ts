import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { invalidateAfterMutation } from "@/lib/mutations";

function keysInvalidated(spy: { mock: { calls: unknown[][] } }) {
  return spy.mock.calls.map((call) => (call[0] as { queryKey: unknown[] }).queryKey);
}

describe("invalidateAfterMutation", () => {
  it("invalidates the application, lists, dashboard and insights when an id is given", async () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);

    await invalidateAfterMutation(queryClient, { applicationId: "app-1" });

    expect(keysInvalidated(spy)).toEqual([
      ["application", "app-1"],
      ["applications"],
      ["interviews"],
      ["communications"],
      ["contacts"],
      ["dashboard"],
      ["insights"],
    ]);
  });

  it("invalidates every application detail when no id is given", async () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);

    await invalidateAfterMutation(queryClient);

    expect(keysInvalidated(spy)[0]).toEqual(["application"]);
  });

  it("marks cached dashboard and insights queries stale so the next read refetches them", async () => {
    const queryClient = new QueryClient();
    const range = {
      preset: "30d" as const,
      range: { start: new Date("2024-06-01T00:00:00Z"), end: new Date("2024-06-30T23:59:59Z") },
    };
    queryClient.setQueryData(["dashboard", ...[range.preset, range.range.start.toISOString(), range.range.end.toISOString()]], {});
    queryClient.setQueryData(["insights", "x"], {});

    await invalidateAfterMutation(queryClient, { applicationId: "app-1" });

    expect(queryClient.getQueryState(["dashboard", range.preset, range.range.start.toISOString(), range.range.end.toISOString()])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["insights", "x"])?.isInvalidated).toBe(true);
  });
});
