import { describe, expect, it } from "vitest";

import {
  CANONICAL_STAGES,
  normalizeStage,
  stageIndex,
  stageProgressPercent,
} from "@/lib/stages";

describe("normalizeStage", () => {
  it("passes canonical stages through unchanged", () => {
    for (const stage of CANONICAL_STAGES) {
      expect(normalizeStage(stage)).toBe(stage);
    }
  });

  it.each([
    ["phone", "screening"],
    ["intro", "screening"],
    ["recruiter", "screening"],
    ["technical", "tech_interview"],
    ["tech", "tech_interview"],
    ["coding", "tech_interview"],
    ["system_design", "tech_interview"],
    ["final", "onsite"],
    ["hired", "offer"],
    ["rejected", "declined"],
    ["declined_archived", "declined"],
  ])("maps the %s alias to %s", (raw, expected) => {
    expect(normalizeStage(raw)).toBe(expected);
  });

  it("normalizes casing, padding and internal whitespace", () => {
    expect(normalizeStage("  System Design  ")).toBe("tech_interview");
    expect(normalizeStage("TECH INTERVIEW")).toBe("tech_interview");
    expect(normalizeStage("Phone")).toBe("screening");
  });

  it("falls back to applied for empty and unknown values", () => {
    expect(normalizeStage(null)).toBe("applied");
    expect(normalizeStage(undefined)).toBe("applied");
    expect(normalizeStage("")).toBe("applied");
    expect(normalizeStage("negotiating-with-legal")).toBe("applied");
  });
});

describe("stageIndex", () => {
  it("returns the canonical ordering position", () => {
    expect(stageIndex("applied")).toBe(0);
    expect(stageIndex("phone")).toBe(1);
    expect(stageIndex("final")).toBe(3);
    expect(stageIndex("declined")).toBe(CANONICAL_STAGES.length - 1);
  });

  it("never returns a negative index", () => {
    expect(stageIndex("who knows")).toBe(0);
  });
});

describe("stageProgressPercent", () => {
  it("scales the stage index across the canonical stage count", () => {
    expect(stageProgressPercent("applied")).toBe(17);
    expect(stageProgressPercent("offer")).toBe(83);
    expect(stageProgressPercent("declined")).toBe(100);
  });

  it("increases monotonically along the canonical stages", () => {
    const percents = CANONICAL_STAGES.map(stageProgressPercent);
    const sorted = [...percents].sort((a, b) => a - b);
    expect(percents).toEqual(sorted);
    expect(new Set(percents).size).toBe(percents.length);
  });

  it("treats unknown stages as the first stage", () => {
    expect(stageProgressPercent("mystery")).toBe(stageProgressPercent("applied"));
  });
});
