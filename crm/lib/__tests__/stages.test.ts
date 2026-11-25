import { describe, expect, it } from "vitest";

import {
  applicationOutcome,
  bestOutcome,
  CANONICAL_STAGES,
  isOpenOutcome,
  isStageChangeEvent,
  isTerminal,
  lookupStage,
  normalizeStage,
  outcomeFromText,
  stageFromEvent,
  stageIndex,
  stageOutcome,
  stageProgress,
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
      ["rejected", "rejected"],
    ["declined_archived", "rejected"],
    ["withdrawn", "withdrawn"],
    ["ghosted", "ghosted"],
  ])("maps the %s alias to %s", (raw, expected) => {
    expect(normalizeStage(raw)).toBe(expected);
  });

  it.each([
    ["  System Design  ", "tech_interview"],
    ["TECH INTERVIEW", "tech_interview"],
    ["Tech-Interview", "tech_interview"],
    ["tech interview", "tech_interview"],
    ["Final-Round", "onsite"],
    ["On_Site", "onsite"],
    ["Phone", "screening"],
    ["OFFER-RECEIVED", "offer"],
    ["Rejected ", "rejected"],
  ])("folds case, whitespace, hyphens and underscores: %j -> %s", (raw, expected) => {
    expect(normalizeStage(raw)).toBe(expected);
  });

  it("falls back to applied for empty and unknown values", () => {
    expect(normalizeStage(null)).toBe("applied");
    expect(normalizeStage(undefined)).toBe("applied");
    expect(normalizeStage("")).toBe("applied");
    expect(normalizeStage("   ")).toBe("applied");
    expect(normalizeStage("negotiating-with-legal")).toBe("applied");
    expect(normalizeStage("constructor")).toBe("applied");
  });

  it("lookupStage returns null for values it does not recognise", () => {
    expect(lookupStage("negotiating-with-legal")).toBeNull();
    expect(lookupStage(null)).toBeNull();
    expect(lookupStage("Hired")).toBe("offer");
  });
});

describe("stageIndex", () => {
  it("returns the pipeline position, -1 for terminal stages", () => {
    expect(stageIndex("applied")).toBe(0);
    expect(stageIndex("phone")).toBe(1);
    expect(stageIndex("final")).toBe(3);
    expect(stageIndex("offer")).toBe(4);
    expect(stageIndex("rejected")).toBe(-1);
    expect(stageIndex("withdrawn")).toBe(-1);
  });

  it("never returns a negative index for unknown values", () => {
    expect(stageIndex("who knows")).toBe(0);
  });
});

describe("isTerminal", () => {
  it("is true for declined, withdrawn and ghosted in any spelling", () => {
    expect(isTerminal("rejected")).toBe(true);
    expect(isTerminal("Rejected")).toBe(true);
    expect(isTerminal("withdrew")).toBe(true);
    expect(isTerminal("ghosting")).toBe(true);
  });

  it("is false for pipeline stages, including offer", () => {
    expect(isTerminal("applied")).toBe(false);
    expect(isTerminal("onsite")).toBe(false);
    expect(isTerminal("offer")).toBe(false);
    expect(isTerminal(null)).toBe(false);
  });
});

describe("stageProgress", () => {
  it("scales progress across the pipeline steps", () => {
    expect(stageProgress("applied")).toEqual({ percent: 20, terminal: null });
    expect(stageProgress("onsite")).toEqual({ percent: 80, terminal: null });
    expect(stageProgress("offer")).toEqual({ percent: 100, terminal: null });
  });

  it("does not show 100% for a declined application", () => {
    expect(stageProgress("rejected")).toEqual({ percent: 20, terminal: "rejected" });
  });

  it("keeps the furthest real step a terminal application reached", () => {
    const history = ["screening", "tech_interview", "rejected"];
    expect(stageProgress("rejected", history)).toEqual({ percent: 60, terminal: "rejected" });
    expect(stageProgress("withdrawn", ["onsite", "withdrawn"])).toEqual({
      percent: 80,
      terminal: "withdrawn",
    });
  });

  it("ignores history entries that are terminal or unknown when finding the furthest step", () => {
    expect(stageProgress("rejected", [null, "ghosted", "mystery"])).toEqual({
      percent: 20,
      terminal: "rejected",
    });
  });

  it("increases monotonically along the pipeline steps", () => {
    const pipeline = ["applied", "screening", "tech_interview", "onsite", "offer"];
    const percents = pipeline.map((stage) => stageProgress(stage).percent);
    expect(percents).toEqual([...percents].sort((a, b) => a - b));
    expect(new Set(percents).size).toBe(percents.length);
  });

  it("treats unknown stages as the first stage", () => {
    expect(stageProgress("mystery")).toEqual(stageProgress("applied"));
  });
});

describe("outcome helpers", () => {
  it("maps a stage to its outcome category", () => {
    expect(stageOutcome("hired")).toBe("offer");
    expect(stageOutcome("rejected")).toBe("rejected");
    expect(stageOutcome("withdrawn")).toBe("withdrawn");
    expect(stageOutcome("ghosted")).toBe("ghosted");
    expect(stageOutcome("tech")).toBe("active");
  });

  it("reads outcome text, returning null for empty or unknown text", () => {
    expect(outcomeFromText("Offer")).toBe("offer");
    expect(outcomeFromText("rejected")).toBe("rejected");
    expect(outcomeFromText("closed")).toBe("rejected");
    expect(outcomeFromText("active")).toBe("active");
    expect(outcomeFromText(null)).toBeNull();
    expect(outcomeFromText("something else")).toBeNull();
  });

  it("prefers an explicit final outcome, then status, then the stage", () => {
    expect(
      applicationOutcome({ status: "active", current_stage: "onsite", outcome: "rejected" })
    ).toBe("rejected");
    expect(
      applicationOutcome({ status: "withdrawn", current_stage: "onsite", outcome: null })
    ).toBe("withdrawn");
    expect(
      applicationOutcome({ status: "active", current_stage: "rejected", outcome: null })
    ).toBe("rejected");
    expect(
      applicationOutcome({ status: "active", current_stage: "offer", outcome: null })
    ).toBe("offer");
    expect(
      applicationOutcome({ status: "active", current_stage: "screening", outcome: null })
    ).toBe("active");
  });

  it("counts offers and open applications as open, terminal outcomes as closed", () => {
    expect(isOpenOutcome("active")).toBe(true);
    expect(isOpenOutcome("offer")).toBe(true);
    expect(isOpenOutcome("rejected")).toBe(false);
    expect(isOpenOutcome("withdrawn")).toBe(false);
    expect(isOpenOutcome("ghosted")).toBe(false);
  });

  it("picks the best outcome across applications: offer > open > withdrawn > ghosted > declined", () => {
    expect(bestOutcome(["rejected", "offer", "active"])).toBe("offer");
    expect(bestOutcome(["rejected", "active"])).toBe("active");
    expect(bestOutcome(["rejected", "withdrawn"])).toBe("withdrawn");
    expect(bestOutcome(["rejected", "ghosted"])).toBe("ghosted");
    expect(bestOutcome(["rejected"])).toBe("rejected");
    expect(bestOutcome([])).toBeNull();
  });
});

describe("stage-change events", () => {
  it.each(["stage_change", "Stage-Change", "stage changed", "stage_changed"])(
    "recognises %s as a stage change",
    (type) => {
      expect(isStageChangeEvent(type)).toBe(true);
    }
  );

  it("does not treat notes, replies or invites as stage changes", () => {
    expect(isStageChangeEvent("reply")).toBe(false);
    expect(isStageChangeEvent("interview_invite")).toBe(false);
    expect(isStageChangeEvent(null)).toBe(false);
  });

  it("reads the target stage from metadata first, then from the title", () => {
    expect(stageFromEvent({ metadata: { to_stage: "onsite" }, title: "Stage → offer" })).toBe(
      "onsite"
    );
    expect(stageFromEvent({ metadata: {}, title: "Stage → declined" })).toBe("declined");
    expect(stageFromEvent({ metadata: null, title: "Stage -> screening" })).toBe("screening");
    expect(stageFromEvent({ metadata: null, title: "Moved on" })).toBeNull();
  });
});
