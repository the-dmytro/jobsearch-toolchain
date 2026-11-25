import type { DateRangeValue } from "@/lib/date-range-context";
import { formatDate } from "@/lib/format";

const STAGE_LABELS: Readonly<Record<string, string>> = {
  applied: "Applied",
  screening: "Screening",
  tech_interview: "Technical interview",
  onsite: "Onsite",
  offer: "Offer",
  declined: "Declined",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
  unknown: "Unknown stage",
};

/** Human label for a stored stage key, for example "tech_interview" becomes "Technical interview". */
export function stageLabel(raw: string | null | undefined): string {
  const key = (raw ?? "").trim().toLowerCase();
  if (!key) return "Unknown stage";
  const known = STAGE_LABELS[key];
  if (known) return known;
  const words = key.replace(/[_-]+/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Lower-case phrase for the selected range, for use inside a sentence. */
export function rangePhrase(value: DateRangeValue): string {
  switch (value.preset) {
    case "7d":
      return "in the last 7 days";
    case "30d":
      return "in the last 30 days";
    case "90d":
      return "in the last 90 days";
    case "all":
      return "in all time";
    default:
      return `from ${formatDate(value.range.start)} to ${formatDate(value.range.end)}`;
  }
}

/** Whether a previous period exists to compare with. "All time" has none. */
export function hasPreviousPeriod(value: DateRangeValue): boolean {
  return value.preset !== "all";
}

/** Signed text for a change, using a true minus sign. Zero is "No change". */
export function signedChange(diff: number, decimals = 0): string {
  const abs = Math.abs(diff).toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (diff > 0) return `+${abs}`;
  if (diff < 0) return `−${abs}`;
  return "0";
}

/**
 * One-line summary of a weekly series for a sparkline's accessible name, for example
 * "Applications per week: 2 in the first week, 5 in the latest week, peak 5."
 */
export function describeTrend(values: readonly number[], label: string): string {
  if (values.length === 0) return `${label}: no weekly data.`;
  const first = values[0];
  const last = values[values.length - 1];
  const peak = Math.max(...values);
  return `${label}: ${first} in the first week, ${last} in the latest week, peak ${peak}.`;
}
