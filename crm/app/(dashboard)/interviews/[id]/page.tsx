import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("interviews")
    .select(
      `
      *,
      applications ( id, opportunity_id ),
      organizations ( name )
    `
    )
    .eq("id", id)
    .single();

  if (error || !row) {
    return <p className="text-destructive">Interview not found</p>;
  }

  const r = row as Record<string, unknown>;
  const app = r.applications as { id?: string } | null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Interview</h1>
          <p className="text-sm text-muted-foreground">{String(r.stage ?? "")}</p>
        </div>
        {app?.id ? (
          <Link
            href={`/applications/${app.id}`}
            className={cn(buttonVariants({ variant: "default" }))}
          >
            Open application
          </Link>
        ) : null}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Notes</CardTitle>
        </CardHeader>
        <CardContent className="whitespace-pre-wrap text-sm">
          {String(r.notes ?? "—")}
        </CardContent>
      </Card>
    </div>
  );
}
