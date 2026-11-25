"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { TableSkeleton } from "@/components/crm/table-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchAll } from "@/lib/fetch-all";
import { formatDate, formatRelative } from "@/lib/format";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export type OpportunityListRow = Tables<"opportunities"> & {
  organizations: { name: string } | null;
};

function toMs(value: string | null | undefined): number {
  const ms = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(ms) ? 0 : ms;
}

export function OpportunitiesPage() {
  const query = useQuery({
    queryKey: qk.opportunities,
    queryFn: async () => {
      const supabase = createClient();
      return fetchAll<OpportunityListRow>((after, limit) => {
        let query = supabase
          .from("opportunities")
          .select(
            `
            *,
            organizations ( name )
          `
          )
          .order("id")
          .limit(limit);
        if (after) query = query.gt("id", after);
        return query;
      }
      );
    },
  });
  const [search, setSearch] = useState("");

  const rows = useMemo(
    () => [...(query.data ?? [])].sort((a, b) => toMs(b.updated_at) - toMs(a.updated_at)),
    [query.data]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      [row.title, row.organizations?.name ?? "", row.location_text ?? "", row.opportunity_type ?? ""].some(
        (text) => text.toLowerCase().includes(q)
      )
    );
  }, [rows, search]);

  const header = (
    <PageHeader
      title="Opportunities"
      description="Job postings you found or were sent, newest first."
      count={query.data ? filtered.length : undefined}
    />
  );

  if (query.isError && !query.data) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState
          title="Opportunities couldn't load"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {!query.data ? (
        <TableSkeleton rows={6} cols={5} label="Loading opportunities" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No opportunities yet"
          description="Opportunities appear here once a search run finds a posting worth evaluating."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="opportunity-search" className="sr-only">
              Search opportunities
            </label>
            <Input
              id="opportunity-search"
              type="search"
              value={search}
              placeholder="Title, company, location or type"
              onChange={(event) => setSearch(event.target.value)}
              className="max-w-md"
            />
            {search ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setSearch("")}>
                Clear search
              </Button>
            ) : null}
          </div>

          {filtered.length === 0 ? (
            <EmptyState title="No opportunities match this search" description="Try a different title or company." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <caption className="sr-only">Opportunities, most recently updated first</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Title</TableHead>
                    <TableHead scope="col">Company</TableHead>
                    <TableHead scope="col">Type</TableHead>
                    <TableHead scope="col">Location</TableHead>
                    <TableHead scope="col">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row) => {
                    const updated = row.updated_at ? toMs(row.updated_at) : null;
                    return (
                      <TableRow key={row.id}>
                        <TableCell>
                          <Link href={`/opportunities/${row.id}`} className="font-medium hover:underline">
                            {row.title || "Untitled opportunity"}
                          </Link>
                        </TableCell>
                        <TableCell>{row.organizations?.name ?? "—"}</TableCell>
                        <TableCell>{row.opportunity_type ?? "—"}</TableCell>
                        <TableCell>{row.location_text ?? "—"}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {updated ? (
                            <time dateTime={row.updated_at ?? undefined} title={formatRelative(updated)}>
                              {formatDate(updated)}
                            </time>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
