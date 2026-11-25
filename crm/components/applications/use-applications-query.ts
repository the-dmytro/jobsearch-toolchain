"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchAll, type KeysetRow } from "@/lib/fetch-all";
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

/** Interview dates and results, for last activity. */
export type ListInterviewRow = Pick<
  Tables<"interviews">,
  "id" | "application_id" | "scheduled_at" | "result"
>;

/** Communication dates and direction, for last activity. */
export type ListCommunicationRow = Pick<
  Tables<"communications">,
  "id" | "application_id" | "direction" | "sent_at" | "created_at"
>;

export type ApplicationsBundle = {
  applications: ApplicationWithJoins[];
  events: StageEventRow[];
  interviews: ListInterviewRow[];
  communications: ListCommunicationRow[];
};

const EVENT_COLUMNS = "id, application_id, event_type, event_at, created_at, metadata, title";
const INTERVIEW_COLUMNS = "id, application_id, scheduled_at, result";
const COMMUNICATION_COLUMNS = "id, application_id, direction, sent_at, created_at";

/**
 * Loads every application with its joins, and every event, interview and communication that feeds
 * last activity. Each table is read with `fetchAll`, so the list is not cut off at PostgREST's cap.
 */
async function fetchApplicationsBundle(): Promise<ApplicationsBundle> {
  const supabase = createClient();
  const [applications, events, interviews, communications] = await Promise.all([
    fetchAll<ApplicationWithJoins & KeysetRow>((after, limit) => {
      let query = supabase
        .from("applications")
        .select(
          `
          *,
          opportunities ( title, source_url ),
          organizations ( name )
        `
        )
        .order("id")
        .limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<StageEventRow & KeysetRow>((after, limit) => {
      let query = supabase.from("application_events").select(EVENT_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<ListInterviewRow & KeysetRow>((after, limit) => {
      let query = supabase.from("interviews").select(INTERVIEW_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<ListCommunicationRow & KeysetRow>((after, limit) => {
      let query = supabase
        .from("communications")
        .select(COMMUNICATION_COLUMNS)
        .order("id")
        .limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
  ]);
  return { applications, events, interviews, communications };
}

export function useApplicationsQuery() {
  return useQuery({
    queryKey: qk.applications,
    queryFn: fetchApplicationsBundle,
  });
}
