"use client";

import { useQuery } from "@tanstack/react-query";
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

async function fetchApplications(): Promise<ApplicationWithJoins[]> {
  const supabase = createClient();
  const { data, error } = await supabase
    .from("applications")
    .select(
      `
      *,
      opportunities ( title, source_url ),
      organizations ( name )
    `
    )
    .order("updated_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as ApplicationWithJoins[];
}

export function useApplicationsQuery() {
  return useQuery({
    queryKey: qk.applications,
    queryFn: fetchApplications,
  });
}
