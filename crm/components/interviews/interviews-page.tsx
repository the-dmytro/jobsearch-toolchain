"use client";

import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import Link from "next/link";
import { useState } from "react";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

export function InterviewsPage() {
  const [month, setMonth] = useState<Date>(new Date());

  const { data: interviews, isLoading, error } = useQuery({
    queryKey: qk.interviews,
    queryFn: async () => {
      const supabase = createClient();
      const { data, error: err } = await supabase
        .from("interviews")
        .select(
          `
          *,
          applications ( id, opportunities(title) ),
          organizations ( name )
        `
        )
        .order("scheduled_at", { ascending: false })
        .limit(200);
      if (err) throw err;
      return data ?? [];
    },
  });

  const datesWithInterviews = new Set<string>();
  for (const i of interviews ?? []) {
    const row = i as { scheduled_at?: string | null };
    if (row.scheduled_at) {
      datesWithInterviews.add(format(new Date(row.scheduled_at), "yyyy-MM-dd"));
    }
  }

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) {
    return (
      <p className="text-destructive">
        {error instanceof Error ? error.message : "Error"}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Interviews</h1>
        <p className="text-sm text-muted-foreground">{interviews?.length ?? 0} scheduled / logged</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Calendar</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center">
            <Calendar
              mode="single"
              month={month}
              onMonthChange={setMonth}
              modifiers={{
                booked: (date) => datesWithInterviews.has(format(date, "yyyy-MM-dd")),
              }}
              modifiersClassNames={{
                booked: "bg-primary/20 font-semibold",
              }}
            />
          </CardContent>
        </Card>

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Company</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(interviews ?? []).map((row: Record<string, unknown>) => {
                const apps = row.applications as {
                  id: string;
                  opportunities: { title?: string } | null;
                } | null;
                const org = row.organizations as { name?: string } | null;
                return (
                  <TableRow key={String(row.id)}>
                    <TableCell className="text-xs whitespace-nowrap">
                      {row.scheduled_at
                        ? format(new Date(String(row.scheduled_at)), "yyyy-MM-dd HH:mm")
                        : "—"}
                    </TableCell>
                    <TableCell>{String(row.stage ?? "—")}</TableCell>
                    <TableCell>
                      {apps?.id ? (
                        <Link
                          href={`/applications/${apps.id}`}
                          className="hover:underline"
                        >
                          {apps.opportunities?.title ?? "Application"}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>{org?.name ?? "—"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
