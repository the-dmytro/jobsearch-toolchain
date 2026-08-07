import { afterEach, describe, expect, it, vi } from "vitest";

import { isDemoMode } from "@/lib/demo";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("isDemoMode", () => {
  it("is true only for the exact string 'true'", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    expect(isDemoMode()).toBe(true);
  });

  it.each(["false", "1", "TRUE", "yes", ""])(
    "is false for the value %o",
    (value) => {
      vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", value);
      expect(isDemoMode()).toBe(false);
    }
  );

  it("is false when the variable is unset", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", undefined);
    expect(isDemoMode()).toBe(false);
  });
});
