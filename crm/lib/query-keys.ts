import type { DateRangeValue } from "@/lib/date-range-context";

function rangeKey(range: DateRangeValue) {
  return [range.preset, range.range.start.toISOString(), range.range.end.toISOString()] as const;
}

export const qk = {
  applications: ["applications"] as const,
  /** Prefix for every application detail query. */
  applicationAll: ["application"] as const,
  application: (id: string) => ["application", id] as const,
  opportunities: ["opportunities"] as const,
  organizations: ["organizations"] as const,
  contacts: ["contacts"] as const,
  interviews: ["interviews"] as const,
  communications: ["communications"] as const,
  runs: ["runs"] as const,
  /** Prefix for every dashboard query, regardless of range. */
  dashboardAll: ["dashboard"] as const,
  dashboard: (range: DateRangeValue) => ["dashboard", ...rangeKey(range)] as const,
  /** Prefix for every insights query, regardless of range. */
  insightsAll: ["insights"] as const,
  insights: (range: DateRangeValue) => ["insights", ...rangeKey(range)] as const,
  artifacts: (relatedType: string, relatedId: string) =>
    ["artifacts", relatedType, relatedId] as const,
  chunks: (artifactId: string) => ["chunks", artifactId] as const,
};
