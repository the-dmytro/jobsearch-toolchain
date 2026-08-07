import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { createClient } from "@/lib/supabase/server";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("automation_runs")
    .select(
      `
      *,
      providers ( name, slug )
    `
    )
    .eq("id", id)
    .single();

  if (error || !row) {
    return <p className="text-destructive">Run not found</p>;
  }

  const r = row as Record<string, unknown>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Automation run</h1>
        <p className="font-mono text-sm text-muted-foreground">{String(r.run_key ?? r.id)}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>Status: {String(r.status)}</p>
          <p>Provider: {(r.providers as { name?: string } | null)?.name ?? "—"}</p>
          <p className="whitespace-pre-wrap">{String(r.summary ?? "—")}</p>
          <p>
            Source items: {String(r.source_items_count)} · Opportunities:{" "}
            {String(r.opportunities_count)} · Evaluations: {String(r.evaluations_count)}
          </p>
          {r.report_email_subject ? (
            <p className="text-muted-foreground">Email: {String(r.report_email_subject)}</p>
          ) : null}
        </CardContent>
      </Card>
      <Link href="/runs" className="text-sm text-primary underline">
        ← All runs
      </Link>
    </div>
  );
}
