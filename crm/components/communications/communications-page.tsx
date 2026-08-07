"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { createCommunication } from "@/lib/actions/communications";
import { qk } from "@/lib/query-keys";
import { communicationInsertSchema } from "@/lib/schemas/communication";
import { createClient } from "@/lib/supabase/client";
import { z } from "zod";

export function CommunicationsPage() {
  const qc = useQueryClient();
  const { data: rows, isLoading, error } = useQuery({
    queryKey: qk.communications,
    queryFn: async () => {
      const supabase = createClient();
      const { data, error: err } = await supabase
        .from("communications")
        .select(
          `
          *,
          organizations ( name ),
          applications ( id )
        `
        )
        .order("sent_at", { ascending: false })
        .limit(200);
      if (err) throw err;
      return data ?? [];
    },
  });

  const { data: apps } = useQuery({
    queryKey: [...qk.applications, "pick"],
    queryFn: async () => {
      const supabase = createClient();
      const { data } = await supabase
        .from("applications")
        .select("id, opportunities(title)")
        .order("updated_at", { ascending: false })
        .limit(100);
      return data ?? [];
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
      if (res && "error" in res) throw new Error(JSON.stringify(res.error));
    },
    onSuccess: () => {
      toast.success("Logged");
      void qc.invalidateQueries({ queryKey: qk.communications });
      form.reset({
        ...form.getValues(),
        subject: "",
        summary: "",
      });
    },
    onError: (e: Error) => toast.error(e.message),
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
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Communications</h1>
        <p className="text-sm text-muted-foreground">{rows?.length ?? 0} rows</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Log communication</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
              className="grid gap-3 sm:grid-cols-2"
            >
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
                          <SelectValue placeholder="Link to application" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="_">None</SelectItem>
                        {(apps ?? []).map(
                          (a: {
                            id: string;
                            opportunities: { title?: string } | null;
                          }) => (
                            <SelectItem key={a.id} value={a.id}>
                              {a.opportunities?.title ?? a.id.slice(0, 8)}
                            </SelectItem>
                          )
                        )}
                      </SelectContent>
                    </Select>
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
                Save
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Subject</TableHead>
              <TableHead>Application</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(rows ?? []).map((row: Record<string, unknown>) => (
              <TableRow key={String(row.id)}>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {String(row.sent_at ?? row.created_at ?? "").slice(0, 16)}
                </TableCell>
                <TableCell>{String(row.subject ?? "—")}</TableCell>
                <TableCell>
                  {(row.applications as { id?: string } | null)?.id ? (
                    <Link
                      href={`/applications/${(row.applications as { id: string }).id}`}
                      className="text-primary hover:underline"
                    >
                      Open
                    </Link>
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
