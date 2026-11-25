"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { CardSkeleton } from "@/components/crm/card-skeleton";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

type ContactDetailData = Tables<"contacts"> & {
  organizations: { id: string; name: string } | null;
};

const INVALID_UUID = "22P02";

export function ContactDetail({ id }: { id: string }) {
  const query = useQuery({
    queryKey: [...qk.contacts, id],
    enabled: !!id,
    queryFn: async (): Promise<ContactDetailData | null> => {
      const supabase = createClient();
      const { data, error } = await supabase
        .from("contacts")
        .select("*, organizations (id, name)")
        .eq("id", id)
        .maybeSingle();
      if (error) {
        if (error.code === INVALID_UUID) return null;
        throw error;
      }
      return (data as ContactDetailData | null) ?? null;
    },
  });

  if (query.isPending) return <CardSkeleton lines={3} label="Loading contact" />;

  if (query.isError) {
    return (
      <div className="space-y-4">
        <ErrorState title="This contact couldn't load" error={query.error} onRetry={() => void query.refetch()} />
        <Link href="/contacts" className={buttonVariants({ variant: "outline", size: "sm" })}>
          Back to contacts
        </Link>
      </div>
    );
  }

  if (!query.data) {
    return (
      <EmptyState
        title="We couldn't find this contact"
        description="It may have been removed, or the link is out of date."
        action={
          <Link href="/contacts" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Back to contacts
          </Link>
        }
      />
    );
  }

  const c = query.data;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link href="/contacts" className="text-sm text-primary underline-offset-4 hover:underline">
          ← Back to contacts
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">{c.full_name ?? "Unnamed contact"}</h1>
        <p className="text-sm text-muted-foreground">{c.role_title ?? "Role not set"}</p>
        {c.organizations?.id ? (
          <Link href={`/companies/${c.organizations.id}`} className="text-sm text-primary underline-offset-4 hover:underline">
            {c.organizations.name}
          </Link>
        ) : null}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p className="break-all">
            <span className="text-muted-foreground">Email: </span>
            {c.email ?? "Not set"}
          </p>
          <p className="break-all">
            <span className="text-muted-foreground">LinkedIn: </span>
            {c.linkedin_url ?? "Not set"}
          </p>
          {c.notes ? <p className="whitespace-pre-wrap pt-2">{c.notes}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
