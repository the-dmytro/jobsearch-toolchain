import Link from "next/link";
import { notFound } from "next/navigation";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatNumber } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import type { Tables } from "@/types/database.types";

type RunDetail = Tables<"automation_runs"> & {
  providers: { name: string; slug: string } | null;
};

/** Postgres rejects a malformed uuid with 22P02. That is a missing record here, not a failure. */
const INVALID_UUID = "22P02";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("automation_runs")
    .select(
      `
      *,
      providers ( name, slug )
    `
    )
    .eq("id", id)
    .maybeSingle();

  if (error && error.code !== INVALID_UUID) {
    throw new Error("This run couldn't be loaded.");
  }
  const row = error ? null : (data as RunDetail | null);
  if (!row) notFound();

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div className="space-y-1">
        <Link href="/runs" className="text-sm text-primary underline-offset-4 hover:underline">
          ← Back to runs
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">Automation run</h1>
        <p className="break-all font-mono text-sm text-muted-foreground">{row.run_key ?? row.id}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Status: </span>
            <span className="capitalize">{row.status.replace(/_/g, " ")}</span>
          </p>
          <p>
            <span className="text-muted-foreground">Provider: </span>
            {row.providers?.name ?? "—"}
          </p>
          <p>
            <span className="text-muted-foreground">Started: </span>
            {formatDate(row.started_at, { withTime: true })}
          </p>
          <p>
            <span className="text-muted-foreground">Finished: </span>
            {formatDate(row.finished_at, { withTime: true })}
          </p>
          <p>
            <span className="text-muted-foreground">Results: </span>
            {formatNumber(row.source_items_count)} sources ·{" "}
            {formatNumber(row.opportunities_count)} opportunities ·{" "}
            {formatNumber(row.evaluations_count)} evaluations
          </p>
          {row.manual_review_count > 0 ? (
            <p>
              <span className="text-muted-foreground">Needs review: </span>
              {formatNumber(row.manual_review_count)}
            </p>
          ) : null}
          {row.report_email_subject ? (
            <p>
              <span className="text-muted-foreground">Report email: </span>
              {row.report_email_subject}
            </p>
          ) : null}
          <p className="whitespace-pre-wrap pt-2">{row.summary ?? "No summary was recorded."}</p>
        </CardContent>
      </Card>
    </div>
  );
}
