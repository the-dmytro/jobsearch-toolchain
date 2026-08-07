"use client";

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

export function CompanyDetail({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...qk.organizations, id],
    queryFn: async () => {
      const supabase = createClient();
      const { data: org, error: e1 } = await supabase
        .from("organizations")
        .select("*")
        .eq("id", id)
        .single();
      if (e1) throw e1;
      const { data: apps } = await supabase
        .from("applications")
        .select("id, status, current_stage, opportunities(title)")
        .eq("organization_id", id);
      const { data: contacts } = await supabase.from("contacts").select("*").eq("organization_id", id);
      const { data: comms } = await supabase
        .from("communications")
        .select("*")
        .eq("organization_id", id)
        .order("sent_at", { ascending: false })
        .limit(20);
      return {
        org,
        apps: apps ?? [],
        contacts: contacts ?? [],
        comms: comms ?? [],
      };
    },
    enabled: !!id,
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (error || !data?.org) {
    return (
      <p className="text-destructive">{error instanceof Error ? error.message : "Not found"}</p>
    );
  }

  const org = data.org as Record<string, unknown>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{String(org.name)}</h1>
        <p className="text-sm text-muted-foreground">{String(org.location_text ?? "—")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Applications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.apps.length === 0 ? (
            <p className="text-sm text-muted-foreground">None</p>
          ) : (
            data.apps.map(
              (a: {
                id: string;
                status: string;
                opportunities: { title?: string } | null;
              }) => (
                <Link
                  key={a.id}
                  href={`/applications/${a.id}`}
                  className="block rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
                >
                  {a.opportunities?.title ?? "Application"} · {a.status}
                </Link>
              )
            )
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Contacts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.contacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">None</p>
          ) : (
            data.contacts.map((c: { id: string; full_name: string | null }) => (
              <Link key={c.id} href={`/contacts/${c.id}`} className="block text-sm hover:underline">
                {c.full_name ?? c.id.slice(0, 8)}
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent communications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {data.comms.length === 0 ? (
            <p className="text-muted-foreground">None</p>
          ) : (
            data.comms.map((c: { id: string; subject: string | null }) => (
              <div key={c.id}>{c.subject ?? "Message"}</div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
