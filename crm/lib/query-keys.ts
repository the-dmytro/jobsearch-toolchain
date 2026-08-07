import type { DateRangeValue } from "@/lib/date-range-context";

export const qk = {
  applications: ["applications"] as const,
  application: (id: string) => ["application", id] as const,
  opportunities: ["opportunities"] as const,
  organizations: ["organizations"] as const,
  contacts: ["contacts"] as const,
  interviews: ["interviews"] as const,
  communications: ["communications"] as const,
  runs: ["runs"] as const,
  insights: (range: DateRangeValue) => ["insights", range.preset, range.range.start.toISOString(), range.range.end.toISOString()] as const,
  dashboard: (range: DateRangeValue) => ["dashboard", range.preset, range.range.start.toISOString(), range.range.end.toISOString()] as const,
  artifacts: (relatedType: string, relatedId: string) =>
    ["artifacts", relatedType, relatedId] as const,
  chunks: (artifactId: string) => ["chunks", artifactId] as const,
};
