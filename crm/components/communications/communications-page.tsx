"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { mutationMessage, unwrapAction } from "@/components/applications/action-error";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { TableSkeleton } from "@/components/crm/table-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { createCommunication } from "@/lib/actions/communications";
import { fetchAll } from "@/lib/fetch-all";
import { formatDate, formatRelative } from "@/lib/format";
import { invalidateAfterMutation } from "@/lib/mutations";
import { qk } from "@/lib/query-keys";
import { communicationInsertSchema } from "@/lib/schemas/communication";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export type CommunicationListRow = Tables<"communications"> & {
  organizations: { name: string } | null;
  applications: { id: string } | null;
};

type ApplicationPick = { id: string; opportunities: { title: string } | null };

function timeOf(row: Pick<Tables<"communications">, "sent_at" | "created_at">): number {
  const ms = Date.parse(row.sent_at ?? row.created_at);
  return Number.isNaN(ms) ? 0 : ms;
}

export function CommunicationsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");

  const listQuery = useQuery({
    queryKey: qk.communications,
    queryFn: async () => {
      const supabase = createClient();
      const rows = await fetchAll<CommunicationListRow>((from, to) =>
        supabase
          .from("communications")
          .select(
            `
            *,
            organizations ( name ),
            applications ( id )
          `
          )
          .order("id")
          .range(from, to)
      );
      return rows.sort((a, b) => timeOf(b) - timeOf(a));
    },
  });

  const appsQuery = useQuery({
    queryKey: [...qk.applications, "pick"],
    queryFn: async () => {
      const supabase = createClient();
      const rows = await fetchAll<ApplicationPick>((from, to) =>
        supabase
          .from("applications")
          .select("id, opportunities(title)")
          .order("id")
          .range(from, to)
      );
      return rows;
    },
  });

  const schema = communicationInsertSchema;
  type FormValues = z.infer<typeof schema>;
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      application_id: null,
      organization_id: null,
      channel: "email",
      direction: "inbound",
      subject: "",
      summary: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async (v: FormValues) => {
      const res = await createCommunication(v);
      unwrapAction(res);
    },
    onSuccess: () => {
      toast.success("Message logged");
      void invalidateAfterMutation(qc);
      form.reset({ ...form.getValues(), subject: "", summary: "" });
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  const rows = listQuery.data;
  const filtered = useMemo(() => {
    const all = rows ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return all;
    return all.filter((row) =>
      [row.subject ?? "", row.summary ?? "", row.organizations?.name ?? ""].some((text) =>
        text.toLowerCase().includes(q)
      )
    );
  }, [rows, search]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Communications"
        description="Messages and calls logged against applications and companies."
        count={rows ? filtered.length : undefined}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Log a message</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit((v) => mutation.mutate(v))} className="grid gap-3 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="application_id"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Application (optional)</FormLabel>
                    <Select
                      onValueChange={(v) => field.onChange(v === "_" ? null : v)}
                      value={field.value ?? "_"}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Link to an application" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="_">None</SelectItem>
                        {(appsQuery.data ?? []).map((a) => (
                          <SelectItem key={a.id} value={a.id}>
                            {a.opportunities?.title ?? "Untitled role"}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {appsQuery.isError ? (
                      <p className="text-xs text-muted-foreground">
                        Applications could not load, so this list may be incomplete.
                      </p>
                    ) : null}
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="subject"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Subject</FormLabel>
                    <FormControl>
                      <Input {...field} value={field.value ?? ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="summary"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Summary</FormLabel>
                    <FormControl>
                      <Textarea {...field} value={field.value ?? ""} rows={3} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Saving…" : "Save message"}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      {listQuery.isError && !rows ? (
        <ErrorState
          title="Messages couldn't load"
          error={listQuery.error}
          onRetry={() => void listQuery.refetch()}
        />
      ) : !rows ? (
        <TableSkeleton rows={6} cols={3} label="Loading messages" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No messages logged yet"
          description="Log an email or call above, or from an application, to keep the history in one place."
        />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="communication-search" className="sr-only">
              Search messages
            </label>
            <Input
              id="communication-search"
              type="search"
              value={search}
              placeholder="Subject, summary or company"
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
            <EmptyState title="No messages match this search" description="Try a different subject or company." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <caption className="sr-only">Logged messages, most recent first</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">When</TableHead>
                    <TableHead scope="col">Subject</TableHead>
                    <TableHead scope="col">Company</TableHead>
                    <TableHead scope="col">Application</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row) => {
                    const when = row.sent_at ?? row.created_at;
                    return (
                      <TableRow key={row.id}>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          <time dateTime={when} title={formatRelative(when)}>
                            {formatDate(when, { withTime: true })}
                          </time>
                        </TableCell>
                        <TableCell>{row.subject ?? "No subject"}</TableCell>
                        <TableCell>{row.organizations?.name ?? "—"}</TableCell>
                        <TableCell>
                          {row.applications?.id ? (
                            <Link href={`/applications/${row.applications.id}`} className="text-primary hover:underline">
                              Open application
                            </Link>
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
        </div>
      )}
    </div>
  );
}
