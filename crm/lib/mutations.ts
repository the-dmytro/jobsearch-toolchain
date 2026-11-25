import type { QueryClient, QueryKey } from "@tanstack/react-query";

import { qk } from "@/lib/query-keys";

export type MutationScope = {
  /** The application a mutation touched. Omit for changes that span applications. */
  applicationId?: string;
};

/**
 * Invalidates every cached query a write to applications, interviews, communications or
 * contacts can change: the dashboard and insights bundles included.
 */
export function invalidateAfterMutation(
  queryClient: QueryClient,
  scope: MutationScope = {}
): Promise<void> {
  const keys: QueryKey[] = [
    scope.applicationId ? qk.application(scope.applicationId) : qk.applicationAll,
    qk.applications,
    qk.interviews,
    qk.communications,
    qk.contacts,
    qk.dashboardAll,
    qk.insightsAll,
  ];
  return Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey }))).then(
    () => undefined
  );
}
