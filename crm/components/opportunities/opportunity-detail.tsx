"use client";

import { SafeExternalLink } from "@/components/crm/safe-external-link";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";

export function OpportunityDetail({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...qk.opportunities, id],
    queryFn: async () => {
      const supabase = createClient();
      const { data: opp, error: e1 } = await supabase
        .from("opportunities")
        .select(
          `
          *,
          organizations (*),
          providers ( slug, name )
        `
        )
        .eq("id", id)
        .single();
      if (e1) throw e1;
      const { data: apps } = await supabase
        .from("applications")
        .select("id, status, current_stage, applied_at")
        .eq("opportunity_id", id);
      const { data: evals } = await supabase
        .from("evaluations")
        .select("*")
        .eq("opportunity_id", id)
        .order("evaluated_at", { ascending: false });
      return { opp, apps: apps ?? [], evals: evals ?? [] };
    },
    enabled: !!id,
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (error || !data?.opp) {
    return (
      <p className="text-destructive">{error instanceof Error ? error.message : "Not found"}</p>
    );
  }

  const o = data.opp as Record<string, unknown>;
  const org = o.organizations as { id?: string; name?: string } | null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{String(o.title)}</h1>
        <p className="text-sm text-muted-foreground">
          {org?.name ?? "—"} · {String(o.opportunity_type ?? "")}
        </p>
        {o.source_url ? (
          <SafeExternalLink
            href={String(o.source_url)}
            className="text-sm text-primary underline"
          >
            Source
          </SafeExternalLink>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Applications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.apps.length === 0 ? (
            <p className="text-sm text-muted-foreground">None</p>
          ) : (
            data.apps.map((a: { id: string; status: string }) => (
              <Link
                key={a.id}
                href={`/applications/${a.id}`}
                className="block rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
              >
                {a.status}
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Evaluations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {data.evals.length === 0 ? (
            <p className="text-muted-foreground">None</p>
          ) : (
            data.evals.map((ev: { id: string; score: number | null }) => (
              <div key={ev.id}>Score: {ev.score ?? "—"}</div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
