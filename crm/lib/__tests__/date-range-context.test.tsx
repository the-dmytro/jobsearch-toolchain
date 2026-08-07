import { endOfDay, startOfDay, subDays } from "date-fns";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  DateRangeProvider,
  useDateRange,
  type DateRangePreset,
} from "@/lib/date-range-context";

const PRESETS: DateRangePreset[] = ["7d", "30d", "90d", "all", "custom"];

function Consumer() {
  const { value, setPreset, setCustomRange } = useDateRange();

  return (
    <div>
      <span data-testid="preset">{value.preset}</span>
      <span data-testid="start">{value.range.start.toISOString()}</span>
      <span data-testid="end">{value.range.end.toISOString()}</span>
      {PRESETS.map((preset) => (
        <button key={preset} onClick={() => setPreset(preset)}>
          {preset}
        </button>
      ))}
      <button
        onClick={() =>
          setCustomRange({
            start: new Date("2024-03-05T13:45:00.000Z"),
            end: new Date("2024-03-09T04:15:00.000Z"),
          })
        }
      >
        set custom range
      </button>
    </div>
  );
}

function renderConsumer() {
  return render(
    <DateRangeProvider>
      <Consumer />
    </DateRangeProvider>
  );
}

function readState() {
  return {
    preset: screen.getByTestId("preset").textContent,
    start: new Date(screen.getByTestId("start").textContent ?? ""),
    end: new Date(screen.getByTestId("end").textContent ?? ""),
  };
}

describe("DateRangeProvider", () => {
  it("defaults to the trailing 30 day window", () => {
    renderConsumer();

    const { preset, start, end } = readState();
    expect(preset).toBe("30d");
    expect(end.toISOString()).toBe(endOfDay(new Date()).toISOString());
    expect(start.toISOString()).toBe(
      startOfDay(subDays(endOfDay(new Date()), 29)).toISOString()
    );
  });

  it.each([
    ["7d", 7],
    ["30d", 30],
    ["90d", 90],
  ])("setPreset(%s) selects a %i day window", async (preset, days) => {
    const user = userEvent.setup();
    renderConsumer();

    await user.click(screen.getByRole("button", { name: preset }));

    const state = readState();
    expect(state.preset).toBe(preset);
    expect(state.start.toISOString()).toBe(
      startOfDay(subDays(endOfDay(new Date()), days - 1)).toISOString()
    );
    expect(state.end.toISOString()).toBe(endOfDay(new Date()).toISOString());
  });

  it("setPreset('all') anchors the window to the epoch start", async () => {
    const user = userEvent.setup();
    renderConsumer();

    await user.click(screen.getByRole("button", { name: "all" }));

    const state = readState();
    expect(state.preset).toBe("all");
    expect(state.start.toISOString()).toBe("2020-01-01T00:00:00.000Z");
    expect(state.end.toISOString()).toBe(endOfDay(new Date()).toISOString());
  });

  it("ignores setPreset('custom') because custom needs explicit bounds", async () => {
    const user = userEvent.setup();
    renderConsumer();

    await user.click(screen.getByRole("button", { name: "90d" }));
    const before = readState();
    await user.click(screen.getByRole("button", { name: "custom" }));

    expect(readState()).toEqual(before);
  });

  it("setCustomRange widens the given dates to whole days", async () => {
    const user = userEvent.setup();
    renderConsumer();

    await user.click(screen.getByRole("button", { name: "set custom range" }));

    const state = readState();
    expect(state.preset).toBe("custom");
    expect(state.start.toISOString()).toBe(
      startOfDay(new Date("2024-03-05T13:45:00.000Z")).toISOString()
    );
    expect(state.end.toISOString()).toBe(
      endOfDay(new Date("2024-03-09T04:15:00.000Z")).toISOString()
    );
  });
});

describe("useDateRange", () => {
  it("throws when rendered outside of a provider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Consumer />)).toThrow(
      "useDateRange must be used within DateRangeProvider"
    );

    consoleError.mockRestore();
  });
});
