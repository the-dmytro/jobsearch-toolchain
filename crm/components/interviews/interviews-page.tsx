"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { TableSkeleton } from "@/components/crm/table-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { formatDate, formatNumber } from "@/lib/format";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

import { InterviewCalendar } from "./interview-calendar";

export type InterviewListRow = Tables<"interviews"> & {
  applications: { id: string; opportunities: { title: string } | null } | null;
  organizations: { name: string } | null;
};

type Row = InterviewListRow & { role: string; company: string; time: number | null };

function toMs(value: string | null): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

function InterviewTable({
  caption,
  rows,
  emptyText,
}: {
  caption: string;
  rows: Row[];
  emptyText: string;
}) {
  return (
    <section aria-label={caption} className="space-y-2">
      <h2 className="text-sm font-semibold">
        {caption} <span className="font-normal tabular-nums text-muted-foreground">({formatNumber(rows.length)})</span>
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <div className="rounded-xl border bg-card">
          <Table>
            <caption className="sr-only">{caption}</caption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">When</TableHead>
                <TableHead scope="col">Stage</TableHead>
                <TableHead scope="col">Role</TableHead>
                <TableHead scope="col">Company</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="whitespace-nowrap text-xs">
                    <Link href={`/interviews/${row.id}`} className="hover:underline">
                      {formatDate(row.scheduled_at, { withTime: true })}
                    </Link>
                  </TableCell>
                  <TableCell>{row.stage ?? "—"}</TableCell>
                  <TableCell>
                    {row.applications?.id ? (
                      <Link href={`/applications/${row.applications.id}`} className="hover:underline">
                        {row.role || "Application"}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>{row.company || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}

export function InterviewsPage() {
  const query = useQuery({
    queryKey: qk.interviews,
    queryFn: async () => {
      const supabase = createClient();
      return fetchAll<InterviewListRow>((from, to) =>
        supabase
          .from("interviews")
          .select(
            `
            *,
            applications ( id, opportunities ( title ) ),
            organizations ( name )
          `
          )
          .order("id")
          .range(from, to)
      );
    },
  });

  const [month, setMonth] = useState(() => new Date());
  const [clockMs] = useState(() => Date.now());
  const [search, setSearch] = useState("");
  const data = query.data;

  const rows = useMemo<Row[]>(
    () =>
      (data ?? []).map((row) => ({
        ...row,
        role: row.applications?.opportunities?.title ?? "",
        company: row.organizations?.name ?? "",
        time: toMs(row.scheduled_at),
      })),
    [data]
  );

  const scheduledAt = useMemo(() => rows.map((row) => row.scheduled_at), [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      [row.role, row.company, row.stage ?? "", row.notes ?? ""].some((text) =>
        text.toLowerCase().includes(q)
      )
    );
  }, [rows, search]);

  // Split by the moment the screen opened, so rows do not change sides while it is open.
  const { upcoming, past } = useMemo(() => {
    const now = clockMs;
    const later: Row[] = [];
    const earlier: Row[] = [];
    for (const row of filtered) {
      if (row.time !== null && row.time >= now) later.push(row);
      else earlier.push(row);
    }
    later.sort((a, b) => (a.time ?? 0) - (b.time ?? 0));
    // Newest first. Rows without a date go last.
    earlier.sort((a, b) => {
      if (a.time === null || b.time === null) return Number(a.time === null) - Number(b.time === null);
      return b.time - a.time;
    });
    return { upcoming: later, past: earlier };
  }, [filtered, clockMs]);

  const header = (
    <PageHeader
      title="Interviews"
      description="Scheduled and logged interviews, split into upcoming and past."
      count={data ? filtered.length : undefined}
    />
  );

  if (query.isError && !data) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState
          title="Interviews couldn't load"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {!data ? (
        <TableSkeleton rows={6} cols={4} label="Loading interviews" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No interviews yet"
          description="Interviews appear here once one is scheduled for an application."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="text-base">Calendar</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center">
              <InterviewCalendar
                scheduledAt={scheduledAt}
                month={month}
                onMonthChange={setMonth}
              />
            </CardContent>
          </Card>

          <div className="space-y-6">
            <div className="space-y-1">
              <label htmlFor="interview-search" className="text-xs font-medium text-muted-foreground">
                Search interviews
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  id="interview-search"
                  type="search"
                  value={search}
                  placeholder="Role, company, stage or notes"
                  onChange={(event) => setSearch(event.target.value)}
                  className="max-w-md"
                />
                {search ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => setSearch("")}>
                    Clear search
                  </Button>
                ) : null}
              </div>
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                title="No interviews match this search"
                description="Try a different role, company or stage."
              />
            ) : (
              <>
                <InterviewTable
                  caption="Upcoming interviews"
                  rows={upcoming}
                  emptyText="Nothing scheduled ahead."
                />
                <InterviewTable
                  caption="Past interviews"
                  rows={past}
                  emptyText="No past interviews match."
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
