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
  /**
   * Every analytics table, read once and range-free. The dashboard and insights compute their
   * bundles from it per date range, so changing the range never refetches.
   */
  analyticsRaw: ["analytics", "raw"] as const,
  artifacts: (relatedType: string, relatedId: string) =>
    ["artifacts", relatedType, relatedId] as const,
  chunks: (artifactId: string) => ["chunks", artifactId] as const,
};
