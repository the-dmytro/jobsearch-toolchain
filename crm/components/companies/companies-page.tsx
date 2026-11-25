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
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export function CompaniesPage() {
  const query = useQuery({
    queryKey: qk.organizations,
    queryFn: async () => {
      const supabase = createClient();
      const rows = await fetchAll<Tables<"organizations">>((after, limit) => {
        let query = supabase.from("organizations").select("*").order("id").limit(limit);
        if (after) query = query.gt("id", after);
        return query;
      }
      );
      return rows.sort((a, b) => a.name.localeCompare(b.name, "en-GB"));
    },
  });
  const [search, setSearch] = useState("");

  const data = query.data;
  const filtered = useMemo(() => {
    const rows = data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      [row.name, row.industry ?? "", row.location_text ?? ""].some((text) => text.toLowerCase().includes(q))
    );
  }, [data, search]);

  const header = (
    <PageHeader
      title="Companies"
      description="Companies you have applied to or talked with, by name."
      count={data ? filtered.length : undefined}
    />
  );

  if (query.isError && !data) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState title="Companies couldn't load" error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {!data ? (
        <TableSkeleton rows={6} cols={3} label="Loading companies" />
      ) : data.length === 0 ? (
        <EmptyState
          title="No companies yet"
          description="A company is added when you apply to a role or log a conversation with it."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="company-search" className="sr-only">
              Search companies
            </label>
            <Input
              id="company-search"
              type="search"
              value={search}
              placeholder="Name, industry or location"
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
            <EmptyState title="No companies match this search" description="Try a different name or industry." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <caption className="sr-only">Companies, A to Z</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Name</TableHead>
                    <TableHead scope="col">Industry</TableHead>
                    <TableHead scope="col">Location</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        <Link href={`/companies/${row.id}`} className="font-medium hover:underline">
                          {row.name}
                        </Link>
                      </TableCell>
                      <TableCell>{row.industry ?? "—"}</TableCell>
                      <TableCell>{row.location_text ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
