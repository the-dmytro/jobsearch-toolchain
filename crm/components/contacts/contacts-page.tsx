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
import { createContact } from "@/lib/actions/contacts";
import { fetchAll } from "@/lib/fetch-all";
import { invalidateAfterMutation } from "@/lib/mutations";
import { qk } from "@/lib/query-keys";
import { contactInsertSchema } from "@/lib/schemas/contact";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export type ContactListRow = Tables<"contacts"> & { organizations: { name: string } | null };

export function ContactsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");

  const contactsQuery = useQuery({
    queryKey: qk.contacts,
    queryFn: async () => {
      const supabase = createClient();
      return fetchAll<ContactListRow>((after, limit) => {
        let query = supabase
          .from("contacts")
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

  const orgsQuery = useQuery({
    queryKey: [...qk.organizations, "pick"],
    queryFn: async () => {
      const supabase = createClient();
      const rows = await fetchAll<{ id: string; name: string }>((after, limit) => {
        let query = supabase.from("organizations").select("id, name").order("id").limit(limit);
        if (after) query = query.gt("id", after);
        return query;
      }
      );
      return rows.sort((a, b) => a.name.localeCompare(b.name, "en-GB"));
    },
  });

  const schema = contactInsertSchema;
  type FormValues = z.infer<typeof schema>;
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      organization_id: null,
      full_name: "",
      email: "",
      role_title: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async (v: FormValues) => {
      const res = await createContact({
        ...v,
        organization_id: v.organization_id ?? null,
        email: v.email === "" ? undefined : v.email,
      });
      unwrapAction(res);
    },
    onSuccess: () => {
      toast.success("Contact added");
      void invalidateAfterMutation(qc);
      form.reset();
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  const contacts = contactsQuery.data;
  const filtered = useMemo(() => {
    const rows = contacts ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      [row.full_name ?? "", row.email ?? "", row.role_title ?? "", row.organizations?.name ?? ""].some((text) =>
        text.toLowerCase().includes(q)
      )
    );
  }, [contacts, search]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Contacts"
        description="People at the companies you are working with."
        count={contacts ? filtered.length : undefined}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add a contact</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
              className="grid gap-3 sm:grid-cols-2"
            >
              <FormField
                control={form.control}
                name="organization_id"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Company</FormLabel>
                    <Select
                      onValueChange={(v) => field.onChange(v === "_" ? null : v)}
                      value={field.value ?? "_"}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Choose a company" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="_">None</SelectItem>
                        {(orgsQuery.data ?? []).map((o) => (
                          <SelectItem key={o.id} value={o.id}>
                            {o.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="full_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} value={field.value ?? ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} value={field.value ?? ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="role_title"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Role</FormLabel>
                    <FormControl>
                      <Input {...field} value={field.value ?? ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Adding…" : "Add contact"}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      {contactsQuery.isError && !contacts ? (
        <ErrorState
          title="Contacts couldn't load"
          error={contactsQuery.error}
          onRetry={() => void contactsQuery.refetch()}
        />
      ) : !contacts ? (
        <TableSkeleton rows={6} cols={3} label="Loading contacts" />
      ) : contacts.length === 0 ? (
        <EmptyState
          title="No contacts yet"
          description="Add a recruiter or hiring manager above to start keeping track of who you talk to."
        />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="contact-search" className="sr-only">
              Search contacts
            </label>
            <Input
              id="contact-search"
              type="search"
              value={search}
              placeholder="Name, email, role or company"
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
            <EmptyState title="No contacts match this search" description="Try a different name or company." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <caption className="sr-only">Contacts, most recently updated first</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Name</TableHead>
                    <TableHead scope="col">Company</TableHead>
                    <TableHead scope="col">Email</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        <Link href={`/contacts/${row.id}`} className="font-medium hover:underline">
                          {row.full_name ?? "Unnamed contact"}
                        </Link>
                      </TableCell>
                      <TableCell>{row.organizations?.name ?? "—"}</TableCell>
                      <TableCell className="break-all">{row.email ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
