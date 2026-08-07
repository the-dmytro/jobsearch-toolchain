"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { qk } from "@/lib/query-keys";
import { createClient } from "@/lib/supabase/client";

export function RunsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: qk.runs,
    queryFn: async () => {
      const supabase = createClient();
      const { data: rows, error: err } = await supabase
        .from("automation_runs")
        .select(
          `
          *,
          providers ( slug, name )
        `
        )
        .order("created_at", { ascending: false })
        .limit(100);
      if (err) throw err;
      return rows ?? [];
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) {
    return (
      <p className="text-destructive">
        {error instanceof Error ? error.message : "Error"}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Automation runs</h1>
        <p className="text-sm text-muted-foreground">{data?.length ?? 0} runs</p>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Run</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Counts</TableHead>
              <TableHead>Finished</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((row: Record<string, unknown>) => (
              <TableRow key={String(row.id)}>
                <TableCell>
                  <Link href={`/runs/${row.id}`} className="font-medium hover:underline">
                    {String(row.run_key ?? row.id).slice(0, 40)}
                  </Link>
                </TableCell>
                <TableCell>
                  {(row.providers as { name?: string } | null)?.name ?? "—"}
                </TableCell>
                <TableCell>{String(row.status)}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  src {String(row.source_items_count)} · opp {String(row.opportunities_count)} · eval{" "}
                  {String(row.evaluations_count)}
                </TableCell>
                <TableCell className="text-xs whitespace-nowrap">
                  {String(row.finished_at ?? row.created_at ?? "").slice(0, 16)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
