"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { addDays, endOfDay, isSameDay, startOfDay, subDays } from "date-fns";

export type DateRangePreset = "7d" | "30d" | "90d" | "all" | "custom";

export type DateRangeBounds = {
  start: Date;
  end: Date;
};

export type DateRangeValue = {
  preset: DateRangePreset;
  range: DateRangeBounds;
};

type DateRangeContextValue = {
  value: DateRangeValue;
  setPreset: (preset: DateRangePreset) => void;
  setCustomRange: (range: DateRangeBounds) => void;
};

const DateRangeContext = createContext<DateRangeContextValue | null>(null);

const ALL_START = new Date("2020-01-01T00:00:00.000Z");

function boundsForPreset(preset: Exclude<DateRangePreset, "custom">): DateRangeBounds {
  const end = endOfDay(new Date());
  if (preset === "all") {
    return { start: ALL_START, end };
  }
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  return { start: startOfDay(subDays(end, days - 1)), end };
}

/** Re-anchors a preset window when the calendar day has changed. Custom ranges are left alone. */
function rollPresetForward(current: DateRangeValue, now: Date): DateRangeValue {
  if (current.preset === "custom") return current;
  if (isSameDay(current.range.end, now)) return current;
  return { preset: current.preset, range: boundsForPreset(current.preset) };
}

export function DateRangeProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<DateRangeValue>(() => ({
    preset: "30d",
    range: boundsForPreset("30d"),
  }));

  // Keep preset windows current across midnight: a timer fires at the next local midnight,
  // and returning to a visible tab re-checks the day in case the timer was throttled.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;

    const roll = () => setValue((current) => rollPresetForward(current, new Date()));

    const scheduleNextMidnight = () => {
      const now = new Date();
      const nextMidnight = startOfDay(addDays(now, 1));
      // A small margin keeps the timer from firing just before midnight on slow clocks.
      const delay = Math.max(0, nextMidnight.getTime() - now.getTime()) + 50;
      timer = setTimeout(() => {
        roll();
        scheduleNextMidnight();
      }, delay);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") roll();
    };

    roll();
    scheduleNextMidnight();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const setPreset = useCallback((preset: DateRangePreset) => {
    if (preset === "custom") return;
    setValue({ preset, range: boundsForPreset(preset) });
  }, []);

  const setCustomRange = useCallback((range: DateRangeBounds) => {
    setValue({
      preset: "custom",
      range: {
        start: startOfDay(range.start),
        end: endOfDay(range.end),
      },
    });
  }, []);

  const contextValue = useMemo(
    () => ({ value, setPreset, setCustomRange }),
    [value, setPreset, setCustomRange]
  );

  return (
    <DateRangeContext.Provider value={contextValue}>{children}</DateRangeContext.Provider>
  );
}

export function useDateRange(): DateRangeContextValue {
  const ctx = useContext(DateRangeContext);
  if (!ctx) {
    throw new Error("useDateRange must be used within DateRangeProvider");
  }
  return ctx;
}
