import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { invalidateAfterMutation } from "@/lib/mutations";

function keysInvalidated(spy: { mock: { calls: unknown[][] } }) {
  return spy.mock.calls.map((call) => (call[0] as { queryKey: unknown[] }).queryKey);
}

describe("invalidateAfterMutation", () => {
  it("invalidates the application, lists, opportunities, organizations and the analytics read when an id is given", async () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);

    await invalidateAfterMutation(queryClient, { applicationId: "app-1" });

    expect(keysInvalidated(spy)).toEqual([
      ["application", "app-1"],
      ["applications"],
      ["interviews"],
      ["communications"],
      ["contacts"],
      ["opportunities"],
      ["organizations"],
      ["analytics", "raw"],
    ]);
  });

  it("invalidates every application detail when no id is given", async () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);

    await invalidateAfterMutation(queryClient);

    expect(keysInvalidated(spy)[0]).toEqual(["application"]);
  });

  it("marks the cached analytics read stale, so the next read refetches it", async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["analytics", "raw"], {});

    await invalidateAfterMutation(queryClient, { applicationId: "app-1" });

    expect(queryClient.getQueryState(["analytics", "raw"])?.isInvalidated).toBe(true);
  });
});
