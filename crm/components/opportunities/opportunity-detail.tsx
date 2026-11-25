"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { CardSkeleton } from "@/components/crm/card-skeleton";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { SafeExternalLink } from "@/components/crm/safe-external-link";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatNumber } from "@/lib/format";
import { normalizeScore } from "@/lib/score";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import { applicationOutcome, normalizeStage } from "@/lib/stages";
import type { Tables } from "@/types/database.types";

type OpportunityDetailData = {
  opportunity: Tables<"opportunities"> & { organizations: { id: string; name: string } | null };
  applications: Pick<Tables<"applications">, "id" | "status" | "current_stage" | "applied_at" | "outcome">[];
  evaluations: Pick<Tables<"evaluations">, "id" | "score" | "evaluated_at">[];
};

const INVALID_UUID = "22P02";

function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className={buttonVariants({ variant: "outline", size: "sm" })}>
      {label}
    </Link>
  );
}

export function OpportunityDetail({ id }: { id: string }) {
  const query = useQuery({
    queryKey: [...qk.opportunities, id],
    enabled: !!id,
    queryFn: async (): Promise<OpportunityDetailData | null> => {
      const supabase = createClient();
      const { data: opportunity, error } = await supabase
        .from("opportunities")
        .select("*, organizations (id, name)")
        .eq("id", id)
        .maybeSingle();
      if (error) {
        if (error.code === INVALID_UUID) return null;
        throw error;
      }
      if (!opportunity) return null;

      const [applications, evaluations] = await Promise.all([
        supabase
          .from("applications")
          .select("id, status, current_stage, applied_at, outcome")
          .eq("opportunity_id", id)
          .order("created_at", { ascending: false }),
        supabase
          .from("evaluations")
          .select("id, score, evaluated_at")
          .eq("opportunity_id", id)
          .order("evaluated_at", { ascending: false }),
      ]);
      if (applications.error) throw applications.error;
      if (evaluations.error) throw evaluations.error;

      return {
        opportunity: opportunity as OpportunityDetailData["opportunity"],
        applications: applications.data ?? [],
        evaluations: evaluations.data ?? [],
      };
    },
  });

  if (query.isPending) return <CardSkeleton lines={4} label="Loading opportunity" />;

  if (query.isError) {
    return (
      <div className="space-y-4">
        <ErrorState title="This opportunity couldn't load" error={query.error} onRetry={() => void query.refetch()} />
        <BackLink href="/opportunities" label="Back to opportunities" />
      </div>
    );
  }

  if (!query.data) {
    return (
      <EmptyState
        title="We couldn't find this opportunity"
        description="It may have been removed, or the link is out of date."
        action={<BackLink href="/opportunities" label="Back to opportunities" />}
      />
    );
  }

  const { opportunity: o, applications, evaluations } = query.data;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link href="/opportunities" className="text-sm text-primary underline-offset-4 hover:underline">
          ← Back to opportunities
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">{o.title || "Untitled opportunity"}</h1>
        <p className="text-sm text-muted-foreground">
          {o.organizations?.name ?? "Company unknown"}
          {o.opportunity_type ? ` · ${o.opportunity_type}` : ""}
        </p>
        {o.source_url ? (
          <SafeExternalLink href={o.source_url} className="text-sm text-primary underline">
            View the posting
          </SafeExternalLink>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Applications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {applications.length === 0 ? (
            <p className="text-sm text-muted-foreground">You have not applied to this role yet.</p>
          ) : (
            applications.map((a) => (
              <Link
                key={a.id}
                href={`/applications/${a.id}`}
                className="block rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
              >
                <span className="capitalize">{normalizeStage(a.current_stage).replace(/_/g, " ")}</span>
                {" · "}
                <span className="capitalize">{applicationOutcome(a)}</span>
                {" · applied "}
                {formatDate(a.applied_at)}
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
          {evaluations.length === 0 ? (
            <p className="text-muted-foreground">No evaluations yet.</p>
          ) : (
            evaluations.map((ev) => (
              <p key={ev.id}>
                Score {normalizeScore(ev.score) === null ? "—" : formatNumber(normalizeScore(ev.score))} · evaluated{" "}
                {formatDate(ev.evaluated_at)}
              </p>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
