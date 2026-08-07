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

export function CompaniesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: qk.organizations,
    queryFn: async () => {
      const supabase = createClient();
      const { data: rows, error: err } = await supabase
        .from("organizations")
        .select("*")
        .order("name");
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
        <h1 className="text-2xl font-semibold">Companies</h1>
        <p className="text-sm text-muted-foreground">{data?.length ?? 0} organizations</p>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Industry</TableHead>
              <TableHead>Location</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((row: Record<string, unknown>) => (
              <TableRow key={String(row.id)}>
                <TableCell>
                  <Link href={`/companies/${row.id}`} className="font-medium hover:underline">
                    {String(row.name)}
                  </Link>
                </TableCell>
                <TableCell>{String(row.industry ?? "—")}</TableCell>
                <TableCell>{String(row.location_text ?? "—")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
