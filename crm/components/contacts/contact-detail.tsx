"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";

export function ContactDetail({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...qk.contacts, id],
    queryFn: async () => {
      const supabase = createClient();
      const { data: row, error: e1 } = await supabase
        .from("contacts")
        .select(
          `
          *,
          organizations (*)
        `
        )
        .eq("id", id)
        .single();
      if (e1) throw e1;
      return row;
    },
    enabled: !!id,
  });

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (error || !data) {
    return (
      <p className="text-destructive">{error instanceof Error ? error.message : "Not found"}</p>
    );
  }

  const c = data as Record<string, unknown>;
  const org = c.organizations as { id?: string; name?: string } | null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{String(c.full_name ?? "Contact")}</h1>
        <p className="text-sm text-muted-foreground">{String(c.role_title ?? "")}</p>
        {org?.id ? (
          <Link href={`/companies/${org.id}`} className="text-sm text-primary underline">
            {org.name}
          </Link>
        ) : null}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>Email: {String(c.email ?? "—")}</p>
          <p>LinkedIn: {String(c.linkedin_url ?? "—")}</p>
          <p className="whitespace-pre-wrap">{String(c.notes ?? "")}</p>
        </CardContent>
      </Card>
    </div>
  );
}
