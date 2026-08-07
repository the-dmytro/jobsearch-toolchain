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

export function OpportunitiesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: qk.opportunities,
    queryFn: async () => {
      const supabase = createClient();
      const { data: rows, error: err } = await supabase
        .from("opportunities")
        .select(
          `
          *,
          organizations ( name )
        `
        )
        .order("updated_at", { ascending: false })
        .limit(300);
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
        <h1 className="text-2xl font-semibold">Opportunities</h1>
        <p className="text-sm text-muted-foreground">{data?.length ?? 0} rows</p>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((row: Record<string, unknown>) => (
              <TableRow key={String(row.id)}>
                <TableCell>
                  <Link
                    href={`/opportunities/${row.id}`}
                    className="font-medium hover:underline"
                  >
                    {String(row.title ?? "")}
                  </Link>
                </TableCell>
                <TableCell>
                  {(row.organizations as { name?: string } | null)?.name ?? "—"}
                </TableCell>
                <TableCell>{String(row.opportunity_type ?? "")}</TableCell>
                <TableCell>{String(row.location_text ?? "—")}</TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {String(row.updated_at ?? "").slice(0, 10)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
