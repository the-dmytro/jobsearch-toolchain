"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAll } from "@/lib/fetch-all";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export type ApplicationWithJoins = Tables<"applications"> & {
  opportunities: {
    title: string;
    source_url: string | null;
  } | null;
  organizations: { name: string } | null;
};

/** The columns the list needs from `application_events`. */
export type StageEventRow = Pick<
  Tables<"application_events">,
  "id" | "application_id" | "event_type" | "event_at" | "created_at" | "metadata" | "title"
>;

export type ApplicationsBundle = {
  applications: ApplicationWithJoins[];
  events: StageEventRow[];
};

const EVENT_COLUMNS = "id, application_id, event_type, event_at, created_at, metadata, title";

/**
 * Loads every application and every event with `fetchAll`, so the list is not
 * cut off at PostgREST's 1000-row cap. Days in stage come from the events.
 */
async function fetchApplicationsBundle(): Promise<ApplicationsBundle> {
  const supabase = createClient();
  const [applications, events] = await Promise.all([
    fetchAll<ApplicationWithJoins>((from, to) =>
      supabase
        .from("applications")
        .select(
          `
          *,
          opportunities ( title, source_url ),
          organizations ( name )
        `
        )
        .order("id")
        .range(from, to)
    ),
    fetchAll<StageEventRow>((from, to) =>
      supabase.from("application_events").select(EVENT_COLUMNS).order("id").range(from, to)
    ),
  ]);
  return { applications, events };
}

export function useApplicationsQuery() {
  return useQuery({
    queryKey: qk.applications,
    queryFn: fetchApplicationsBundle,
  });
}
