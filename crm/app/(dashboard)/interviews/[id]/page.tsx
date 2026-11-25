import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";
import type { Tables } from "@/types/database.types";

type InterviewDetail = Tables<"interviews"> & {
  applications: { id: string; opportunities: { title: string } | null } | null;
  organizations: { name: string } | null;
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
    .from("interviews")
    .select(
      `
      *,
      applications ( id, opportunities ( title ) ),
      organizations ( name )
    `
    )
    .eq("id", id)
    .maybeSingle();

  if (error && error.code !== INVALID_UUID) {
    throw new Error("This interview couldn't be loaded.");
  }
  const row = error ? null : (data as InterviewDetail | null);
  if (!row) notFound();

  const applicationId = row.applications?.id ?? null;
  const role = row.applications?.opportunities?.title ?? "Application";

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div className="space-y-1">
        <Link href="/interviews" className="text-sm text-primary underline-offset-4 hover:underline">
          ← Back to interviews
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Interview</h1>
          {row.stage ? <Badge variant="secondary">{row.stage}</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground">
          {role}
          {row.organizations?.name ? ` · ${row.organizations.name}` : ""}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Scheduled: </span>
            {formatDate(row.scheduled_at, { withTime: true })}
          </p>
          {row.completed_at ? (
            <p>
              <span className="text-muted-foreground">Completed: </span>
              {formatDate(row.completed_at, { withTime: true })}
            </p>
          ) : null}
          {row.meeting_url ? (
            <p className="break-all">
              <span className="text-muted-foreground">Meeting link: </span>
              {row.meeting_url}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Notes</CardTitle>
        </CardHeader>
        <CardContent className="whitespace-pre-wrap text-sm">
          {row.notes ?? "No notes yet."}
        </CardContent>
      </Card>

      {applicationId ? (
        <Link href={`/applications/${applicationId}`} className={cn(buttonVariants({ variant: "default" }))}>
          Open application
        </Link>
      ) : null}
    </div>
  );
}
