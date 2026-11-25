import { describe, expect, it } from "vitest";
import { compareRunsNewestFirst, runKeyTime, runTime, type RunTimeSource } from "@/lib/run-time";

function source(overrides: Partial<RunTimeSource> = {}): RunTimeSource {
  return { started_at: null, finished_at: null, run_key: null, ...overrides };
}

const utc = (year: number, month: number, day: number, hour = 0, minute = 0, second = 0) =>
  Date.UTC(year, month - 1, day, hour, minute, second);

describe("runTime", () => {
  it("prefers started_at, then finished_at, then the run key", () => {
    expect(
      runTime(source({ started_at: "2026-05-22T01:00:00.000Z", finished_at: "2026-05-22T02:00:00.000Z", run_key: "x-20260101000000" }))
    ).toBe(utc(2026, 5, 22, 1));
    expect(runTime(source({ finished_at: "2026-05-22T02:00:00.000Z", run_key: "x-20260101000000" }))).toBe(utc(2026, 5, 22, 2));
    expect(runTime(source({ run_key: "linkedin-mail-fetch-20260522013805" }))).toBe(utc(2026, 5, 22, 1, 38, 5));
  });

  it("returns null when no time is recorded, never falling back to a write timestamp", () => {
    expect(runTime(source({ run_key: "manual-run" }))).toBeNull();
    expect(runTime(source())).toBeNull();
  });
});

describe("runKeyTime", () => {
  it("reads a trailing 14-digit stamp as UTC", () => {
    expect(runKeyTime("linkedin-mail-fetch-20260522013805")).toBe(utc(2026, 5, 22, 1, 38, 5));
  });

  it("reads a trailing 12-digit stamp as UTC, with no seconds", () => {
    expect(runKeyTime("upwork-mail-fetch-202606040709")).toBe(utc(2026, 6, 4, 7, 9));
  });

  it("reads a YYYY-MM-DD date anywhere in the key as UTC midnight", () => {
    expect(runKeyTime("djinni-data-ml-ai-jobboards-2026-11-19")).toBe(utc(2026, 11, 19));
    expect(runKeyTime("linkedin-2026-05-07")).toBe(utc(2026, 5, 7));
  });

  it("ignores digits that are not a whole trailing stamp", () => {
    expect(runKeyTime("run-120260522013805")).toBeNull();
    expect(runKeyTime("run-202605220138050")).toBeNull();
  });

  it("rejects stamps that are not real dates", () => {
    expect(runKeyTime("fetch-20261340250000")).toBeNull();
    expect(runKeyTime("fetch-2026-02-31")).toBeNull();
  });

  it("returns null for empty or missing keys", () => {
    expect(runKeyTime(null)).toBeNull();
    expect(runKeyTime(undefined)).toBeNull();
    expect(runKeyTime("")).toBeNull();
  });
});

describe("compareRunsNewestFirst", () => {
  it("orders by runTime, newest first, with untimed runs last", () => {
    const runs = [
      source({ run_key: "untimed" }),
      source({ run_key: "a-2026-05-01" }),
      source({ started_at: "2026-05-20T00:00:00.000Z" }),
      source({ run_key: "b-2026-05-10" }),
    ];

    const ordered = [...runs].sort(compareRunsNewestFirst);

    expect(ordered.map(runTime)).toEqual([utc(2026, 5, 20), utc(2026, 5, 10), utc(2026, 5, 1), null]);
  });
});
