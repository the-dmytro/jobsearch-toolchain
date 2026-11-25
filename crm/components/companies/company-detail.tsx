"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { CardSkeleton } from "@/components/crm/card-skeleton";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

type CompanyDetailData = {
  org: Tables<"organizations">;
  apps: { id: string; status: string; current_stage: string | null; opportunities: { title: string } | null }[];
  contacts: Pick<Tables<"contacts">, "id" | "full_name">[];
  comms: Pick<Tables<"communications">, "id" | "subject" | "sent_at">[];
};

const INVALID_UUID = "22P02";

export function CompanyDetail({ id }: { id: string }) {
  const query = useQuery({
    queryKey: [...qk.organizations, id],
    enabled: !!id,
    queryFn: async (): Promise<CompanyDetailData | null> => {
      const supabase = createClient();
      const { data: org, error } = await supabase
        .from("organizations")
        .select("*")
        .eq("id", id)
        .maybeSingle();
      if (error) {
        if (error.code === INVALID_UUID) return null;
        throw error;
      }
      if (!org) return null;

      const [apps, contacts, comms] = await Promise.all([
        supabase
          .from("applications")
          .select("id, status, current_stage, opportunities(title)")
          .eq("organization_id", id)
          .order("created_at", { ascending: false }),
        supabase.from("contacts").select("id, full_name").eq("organization_id", id).order("full_name"),
        supabase
          .from("communications")
          .select("id, subject, sent_at")
          .eq("organization_id", id)
          .order("sent_at", { ascending: false })
          .limit(20),
      ]);
      for (const result of [apps, contacts, comms]) {
        if (result.error) throw result.error;
      }

      return {
        org,
        apps: (apps.data ?? []) as CompanyDetailData["apps"],
        contacts: contacts.data ?? [],
        comms: comms.data ?? [],
      };
    },
  });

  if (query.isPending) return <CardSkeleton lines={4} label="Loading company" />;

  if (query.isError) {
    return (
      <div className="space-y-4">
        <ErrorState title="This company couldn't load" error={query.error} onRetry={() => void query.refetch()} />
        <Link href="/companies" className={buttonVariants({ variant: "outline", size: "sm" })}>
          Back to companies
        </Link>
      </div>
    );
  }

  if (!query.data) {
    return (
      <EmptyState
        title="We couldn't find this company"
        description="It may have been removed, or the link is out of date."
        action={
          <Link href="/companies" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Back to companies
          </Link>
        }
      />
    );
  }

  const { org, apps, contacts, comms } = query.data;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link href="/companies" className="text-sm text-primary underline-offset-4 hover:underline">
          ← Back to companies
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">{org.name}</h1>
        <p className="text-sm text-muted-foreground">{org.location_text ?? "Location not set"}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Applications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {apps.length === 0 ? (
            <p className="text-sm text-muted-foreground">No applications for this company yet.</p>
          ) : (
            apps.map((a) => (
              <Link
                key={a.id}
                href={`/applications/${a.id}`}
                className="block rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
              >
                {a.opportunities?.title ?? "Application"} · <span className="capitalize">{a.status}</span>
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Contacts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {contacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No contacts here yet.</p>
          ) : (
            contacts.map((c) => (
              <Link key={c.id} href={`/contacts/${c.id}`} className="block text-sm hover:underline">
                {c.full_name ?? "Contact"}
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
          {comms.length === 0 ? (
            <p className="text-muted-foreground">No messages logged yet.</p>
          ) : (
            comms.map((c) => (
              <p key={c.id}>
                {c.subject ?? "Message"}
                {c.sent_at ? <span className="text-muted-foreground"> · {formatDate(c.sent_at)}</span> : null}
              </p>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
