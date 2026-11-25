"use client";

import { format } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { type DateRange as DayPickerRange } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  type DateRangePreset,
  useDateRange,
} from "@/lib/date-range-context";

const PRESETS: { label: string; value: Exclude<DateRangePreset, "custom"> }[] = [
  { label: "7 days", value: "7d" },
  { label: "30 days", value: "30d" },
  { label: "90 days", value: "90d" },
  { label: "All time", value: "all" },
];

/**
 * Chooses the dashboard date range: quick presets plus a custom calendar.
 *
 * From 640px up, presets are a segmented button group. Below that they collapse
 * into a select, so the control keeps every option at 375px. The custom range
 * opens a calendar popover on every screen size.
 */
export function DateRangePicker() {
  const { value, setPreset, setCustomRange } = useDateRange();

  const calendarRange: DayPickerRange = {
    from: value.range.start,
    to: value.range.end,
  };
  const rangeLabel = `${format(value.range.start, "MMM d")} – ${format(value.range.end, "MMM d, yyyy")}`;

  return (
    <div className="flex items-center gap-1">
      <div
        role="group"
        aria-label="Quick date ranges"
        className="hidden items-center rounded-md border p-0.5 sm:flex"
      >
        {PRESETS.map((preset) => {
          const selected = value.preset === preset.value;
          return (
            <Button
              key={preset.value}
              type="button"
              variant={selected ? "secondary" : "ghost"}
              size="sm"
              aria-pressed={selected}
              className="h-7 px-2.5 text-xs"
              onClick={() => setPreset(preset.value)}
            >
              {preset.label}
            </Button>
          );
        })}
      </div>
      <select
        aria-label="Quick date range"
        value={value.preset}
        onChange={(event) => {
          const next = event.target.value as Exclude<DateRangePreset, "custom">;
          setPreset(next);
        }}
        className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:hidden"
      >
        {value.preset === "custom" ? (
          <option value="custom" disabled>
            Custom range
          </option>
        ) : null}
        {PRESETS.map((preset) => (
          <option key={preset.value} value={preset.value}>
            {preset.label}
          </option>
        ))}
      </select>
      <Popover>
        <PopoverTrigger
          render={
            <Button variant="outline" size="sm" className="h-8 justify-start gap-2 font-normal">
              <CalendarIcon aria-hidden="true" className="size-3.5" />
              <span className="hidden tabular-nums sm:inline">{rangeLabel}</span>
              <span className="sr-only sm:hidden">Pick a custom date range</span>
            </Button>
          }
        />
        <PopoverContent className="w-auto p-0" align="end">
          <Calendar
            mode="range"
            selected={calendarRange}
            onSelect={(range) => {
              if (range?.from && range?.to) {
                setCustomRange({ start: range.from, end: range.to });
              }
            }}
            numberOfMonths={2}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
