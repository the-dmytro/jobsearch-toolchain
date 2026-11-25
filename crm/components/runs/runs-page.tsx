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
import { formatDate, formatNumber, formatRelative } from "@/lib/format";
import { qk } from "@/lib/query-keys";
import { compareRunsNewestFirst, runTime } from "@/lib/run-time";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export type RunRow = Tables<"automation_runs"> & {
  providers: { slug: string; name: string } | null;
};

export function RunsPage() {
  const query = useQuery({
    queryKey: qk.runs,
    queryFn: async () => {
      const supabase = createClient();
      return fetchAll<RunRow>((after, limit) => {
        let query = supabase
          .from("automation_runs")
          .select(
            `
            *,
            providers ( slug, name )
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

  const sorted = useMemo(() => [...(query.data ?? [])].sort(compareRunsNewestFirst), [query.data]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((row) =>
      [row.run_key ?? "", row.id, row.providers?.name ?? "", row.status, row.summary ?? ""].some(
        (text) => text.toLowerCase().includes(q)
      )
    );
  }, [sorted, search]);

  const header = (
    <PageHeader
      title="Automation runs"
      description="Recent searches and their results, newest first."
      count={query.data ? filtered.length : undefined}
    />
  );

  if (query.isError && !query.data) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState title="Runs couldn't load" error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {!query.data ? (
        <TableSkeleton rows={6} cols={5} label="Loading runs" />
      ) : sorted.length === 0 ? (
        <EmptyState
          title="No runs yet"
          description="Runs appear here after an automated search has finished at least once."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="run-search" className="sr-only">
              Search runs
            </label>
            <Input
              id="run-search"
              type="search"
              value={search}
              placeholder="Run, provider, status or summary"
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
            <EmptyState title="No runs match this search" description="Try a different provider or status." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <caption className="sr-only">Automation runs, newest first</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Run</TableHead>
                    <TableHead scope="col">Provider</TableHead>
                    <TableHead scope="col">Status</TableHead>
                    <TableHead scope="col">Results</TableHead>
                    <TableHead scope="col">Run time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row) => {
                    const time = runTime(row);
                    return (
                      <TableRow key={row.id}>
                        <TableCell>
                          <Link href={`/runs/${row.id}`} className="font-medium hover:underline">
                            {row.run_key ?? "Run"}
                          </Link>
                        </TableCell>
                        <TableCell>{row.providers?.name ?? "—"}</TableCell>
                        <TableCell className="capitalize">{row.status.replace(/_/g, " ")}</TableCell>
                        <TableCell className="text-xs tabular-nums text-muted-foreground">
                          {formatNumber(row.source_items_count)} sources ·{" "}
                          {formatNumber(row.opportunities_count)} opportunities ·{" "}
                          {formatNumber(row.evaluations_count)} evaluations
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs">
                          {time === null ? (
                            <span className="text-muted-foreground">Time not recorded</span>
                          ) : (
                            <time dateTime={new Date(time).toISOString()} title={formatRelative(time)}>
                              {formatDate(time, { withTime: true })}
                            </time>
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
