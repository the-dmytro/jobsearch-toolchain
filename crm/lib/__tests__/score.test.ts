import { describe, expect, it } from "vitest";
import { normalizeScore } from "@/lib/score";

describe("normalizeScore", () => {
  it("returns null for missing and non-finite values", () => {
    expect(normalizeScore(null)).toBeNull();
    expect(normalizeScore(undefined)).toBeNull();
    expect(normalizeScore(Number.NaN)).toBeNull();
    expect(normalizeScore(Number.POSITIVE_INFINITY)).toBeNull();
  });

  it("keeps values already on the 0 to 10 scale", () => {
    expect(normalizeScore(0)).toBe(0);
    expect(normalizeScore(7.5)).toBe(7.5);
    expect(normalizeScore(10)).toBe(10);
  });

  it("divides values above ten by ten, for the 0 to 100 rows", () => {
    expect(normalizeScore(85)).toBe(8.5);
    expect(normalizeScore(11)).toBe(1.1);
    expect(normalizeScore(100)).toBe(10);
  });

  it("clamps the result to 0 to 10", () => {
    expect(normalizeScore(-3)).toBe(0);
    expect(normalizeScore(250)).toBe(10);
  });
});
