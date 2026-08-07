"use client";

import { useQuery } from "@tanstack/react-query";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export type ApplicationDetailApp = Tables<"applications"> & {
  opportunities: Tables<"opportunities"> | null;
  organizations: Tables<"organizations"> | null;
  providers: { slug: string; name: string } | null;
};

export type ApplicationDetailBundle = {
  application: ApplicationDetailApp;
  events: Tables<"application_events">[];
  communications: Tables<"communications">[];
  interviews: Tables<"interviews">[];
  evaluations: Tables<"evaluations">[];
  sourceItems: Tables<"source_items">[];
  contacts: Tables<"contacts">[];
  artifacts: Tables<"artifacts">[];
  chunksByArtifactId: Record<string, Tables<"document_chunks">[]>;
};

async function fetchBundle(id: string): Promise<ApplicationDetailBundle> {
  const supabase = createClient();

  const { data: application, error: appErr } = await supabase
    .from("applications")
    .select(
      `
      *,
      opportunities (*),
      organizations (*),
      providers ( slug, name )
    `
    )
    .eq("id", id)
    .single();

  if (appErr) throw appErr;
  const app = application as ApplicationDetailApp;
  const oppId = app.opportunity_id;
  const orgId = app.organization_id;

  const [eventsRes, commRes, intRes, evalRes, siRes, contactsRes, artAppRes] =
    await Promise.all([
      supabase
        .from("application_events")
        .select("*")
        .eq("application_id", id)
        .order("created_at", { ascending: false }),
      supabase
        .from("communications")
        .select("*")
        .eq("application_id", id)
        .order("sent_at", { ascending: false }),
      supabase
        .from("interviews")
        .select("*")
        .eq("application_id", id)
        .order("scheduled_at", { ascending: false }),
      oppId
        ? supabase
            .from("evaluations")
            .select("*")
            .eq("opportunity_id", oppId)
            .order("evaluated_at", { ascending: false })
        : Promise.resolve({ data: [] as Tables<"evaluations">[], error: null }),
      oppId
        ? supabase
            .from("source_items")
            .select("*")
            .eq("opportunity_id", oppId)
            .order("created_at", { ascending: false })
        : Promise.resolve({ data: [] as Tables<"source_items">[], error: null }),
      orgId
        ? supabase.from("contacts").select("*").eq("organization_id", orgId)
        : Promise.resolve({ data: [] as Tables<"contacts">[], error: null }),
      supabase
        .from("artifacts")
        .select("*")
        .eq("related_type", "application")
        .eq("related_id", id),
    ]);

  const intRows = (intRes.data ?? []) as Tables<"interviews">[];
  const transcriptIds = intRows.map((r) => r.transcript_artifact_id).filter(Boolean) as string[];

  let transcriptArtifacts: Tables<"artifacts">[] = [];
  const chunksByArtifactId: Record<string, Tables<"document_chunks">[]> = {};

  if (transcriptIds.length) {
    const { data: ta } = await supabase
      .from("artifacts")
      .select("*")
      .in("id", transcriptIds);
    transcriptArtifacts = (ta ?? []) as Tables<"artifacts">[];

    const { data: chunks } = await supabase
      .from("document_chunks")
      .select("*")
      .in("artifact_id", transcriptIds)
      .order("chunk_index", { ascending: true });
    for (const c of chunks ?? []) {
      const aid = c.artifact_id;
      if (!chunksByArtifactId[aid]) chunksByArtifactId[aid] = [];
      chunksByArtifactId[aid].push(c as Tables<"document_chunks">);
    }
  }

  const seen = new Set<string>();
  const artifacts: Tables<"artifacts">[] = [];
  for (const a of [
    ...((artAppRes.data ?? []) as Tables<"artifacts">[]),
    ...transcriptArtifacts,
  ]) {
    if (!seen.has(a.id)) {
      seen.add(a.id);
      artifacts.push(a);
    }
  }

  return {
    application: app,
    events: (eventsRes.data ?? []) as Tables<"application_events">[],
    communications: (commRes.data ?? []) as Tables<"communications">[],
    interviews: intRows,
    evaluations: (evalRes.data ?? []) as Tables<"evaluations">[],
    sourceItems: (siRes.data ?? []) as Tables<"source_items">[],
    contacts: (contactsRes.data ?? []) as Tables<"contacts">[],
    artifacts,
    chunksByArtifactId,
  };
}

export function useApplicationDetail(id: string) {
  return useQuery({
    queryKey: qk.application(id),
    queryFn: () => fetchBundle(id),
    enabled: !!id,
  });
}
