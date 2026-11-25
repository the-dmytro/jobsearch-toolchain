"use client";

import { format } from "date-fns";
import { createContext, useContext, useMemo, type ComponentProps } from "react";
import type { DayButton } from "react-day-picker";

import { CalendarDayButton, Calendar } from "@/components/ui/calendar";
import { formatDate } from "@/lib/format";

/** Local calendar day as yyyy-MM-dd, the key used to count interviews per day. */
export function dayKey(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

/** Number of interviews per local day. Dates that are missing or invalid are skipped. */
export function countInterviewsByDay(
  scheduledAt: readonly (string | null | undefined)[]
): Map<string, number> {
  const counts = new Map<string, number>();
  for (const value of scheduledAt) {
    if (!value) continue;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) continue;
    const key = dayKey(date);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

const CountsContext = createContext<ReadonlyMap<string, number>>(new Map());

/**
 * A day with interviews gets a dot and an accessible name that says how many
 * there are. The tint is not the only signal.
 */
function InterviewDayButton(props: ComponentProps<typeof DayButton>) {
  const counts = useContext(CountsContext);
  const { day, children, ...rest } = props;
  const count = counts.get(dayKey(day.date)) ?? 0;
  const label =
    count > 0
      ? `${formatDate(day.date)}, ${count} ${count === 1 ? "interview" : "interviews"}`
      : rest["aria-label"];
  return (
    <CalendarDayButton {...rest} day={day} aria-label={label}>
      {children}
      {count > 0 ? <span aria-hidden="true" className="size-1 rounded-full bg-primary" /> : null}
    </CalendarDayButton>
  );
}

/**
 * Month view with a dot on each day that has interviews. A legend under the
 * calendar explains the dot for sighted users.
 */
export function InterviewCalendar({
  scheduledAt,
  month,
  onMonthChange,
}: {
  scheduledAt: readonly (string | null | undefined)[];
  month: Date;
  onMonthChange: (month: Date) => void;
}) {
  const counts = useMemo(() => countInterviewsByDay(scheduledAt), [scheduledAt]);
  return (
    <CountsContext.Provider value={counts}>
      <Calendar
        mode="single"
        month={month}
        onMonthChange={onMonthChange}
        components={{ DayButton: InterviewDayButton }}
        modifiers={{ booked: (date) => counts.has(dayKey(date)) }}
        modifiersClassNames={{ booked: "font-semibold" }}
      />
      <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-primary" />
        Days with an interview are marked with a dot.
      </p>
    </CountsContext.Provider>
  );
}
