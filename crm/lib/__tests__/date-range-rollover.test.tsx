import { act, fireEvent, render, screen } from "@testing-library/react";
import { isSameDay } from "date-fns";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DateRangeProvider, useDateRange } from "@/lib/date-range-context";

function Consumer() {
  const { value, setCustomRange } = useDateRange();
  return (
    <div>
      <span data-testid="preset">{value.preset}</span>
      <span data-testid="end">{value.range.end.toISOString()}</span>
      <button
        onClick={() =>
          setCustomRange({
            start: new Date(2024, 2, 1),
            end: new Date(2024, 2, 5),
          })
        }
      >
        set custom
      </button>
    </div>
  );
}

function renderProvider() {
  return render(
    <DateRangeProvider>
      <Consumer />
    </DateRangeProvider>
  );
}

function endDate(): Date {
  return new Date(screen.getByTestId("end").textContent ?? "");
}

const LATE_EVENING = new Date(2024, 2, 10, 22, 0, 0, 0);

describe("DateRangeProvider midnight rollover", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
    vi.setSystemTime(LATE_EVENING);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("moves a preset window to the new day at local midnight", () => {
    renderProvider();
    expect(isSameDay(endDate(), new Date(2024, 2, 10))).toBe(true);

    act(() => {
      vi.advanceTimersByTime(2 * 60 * 60 * 1000 + 1000);
    });

    expect(isSameDay(endDate(), new Date(2024, 2, 11))).toBe(true);
  });

  it("keeps rolling over on later days, not just the first midnight", () => {
    renderProvider();

    act(() => {
      vi.advanceTimersByTime(2 * 60 * 60 * 1000 + 1000);
    });
    act(() => {
      vi.advanceTimersByTime(24 * 60 * 60 * 1000);
    });

    expect(isSameDay(endDate(), new Date(2024, 2, 12))).toBe(true);
  });

  it("re-checks the day when the tab becomes visible again", () => {
    renderProvider();

    // Simulate a throttled timer: the clock moves on but the timer has not fired yet.
    vi.setSystemTime(new Date(2024, 2, 12, 8, 0, 0, 0));
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    visibility.mockRestore();

    expect(isSameDay(endDate(), new Date(2024, 2, 12))).toBe(true);
  });

  it("leaves a custom range alone at midnight", () => {
    renderProvider();
    fireEvent.click(screen.getByRole("button", { name: "set custom" }));
    const customEnd = screen.getByTestId("end").textContent;

    act(() => {
      vi.advanceTimersByTime(3 * 24 * 60 * 60 * 1000);
    });

    expect(screen.getByTestId("preset").textContent).toBe("custom");
    expect(screen.getByTestId("end").textContent).toBe(customEnd);
  });

  it("does not re-render when the day has not changed", () => {
    renderProvider();
    const before = screen.getByTestId("end").textContent;

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(screen.getByTestId("end").textContent).toBe(before);
  });
});
