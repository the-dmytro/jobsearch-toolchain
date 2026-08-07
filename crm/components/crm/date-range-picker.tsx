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
import { cn } from "@/lib/utils";

const PRESETS: { label: string; value: DateRangePreset }[] = [
  { label: "7d", value: "7d" },
  { label: "30d", value: "30d" },
  { label: "90d", value: "90d" },
  { label: "All", value: "all" },
];

export function DateRangePicker() {
  const { value, setPreset, setCustomRange } = useDateRange();

  const calendarRange: DayPickerRange = {
    from: value.range.start,
    to: value.range.end,
  };

  return (
    <div className="flex items-center gap-1">
      <div className="hidden items-center rounded-md border p-0.5 sm:flex">
        {PRESETS.map((preset) => (
          <Button
            key={preset.value}
            variant={value.preset === preset.value ? "secondary" : "ghost"}
            size="sm"
            className="h-7 px-2.5 text-xs"
            onClick={() => setPreset(preset.value)}
          >
            {preset.label}
          </Button>
        ))}
      </div>
      <Popover>
        <PopoverTrigger
          render={
            <Button
              variant="outline"
              size="sm"
              className={cn("h-8 justify-start gap-2 font-normal")}
            >
              <CalendarIcon className="size-3.5" />
              <span className="hidden sm:inline">
                {format(value.range.start, "MMM d")} – {format(value.range.end, "MMM d, yyyy")}
              </span>
              <span className="sm:hidden">{value.preset}</span>
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
