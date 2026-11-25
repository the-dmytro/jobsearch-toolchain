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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { createContact } from "@/lib/actions/contacts";
import { invalidateAfterMutation } from "@/lib/mutations";
import { qk } from "@/lib/query-keys";
import { contactInsertSchema } from "@/lib/schemas/contact";
import { createClient } from "@/lib/supabase/client";
import { z } from "zod";

export function ContactsPage() {
  const qc = useQueryClient();
  const { data: contacts, isLoading, error } = useQuery({
    queryKey: qk.contacts,
    queryFn: async () => {
      const supabase = createClient();
      const { data: rows, error: err } = await supabase
        .from("contacts")
        .select(
          `
          *,
          organizations ( name )
        `
        )
        .order("updated_at", { ascending: false });
      if (err) throw err;
      return rows ?? [];
    },
  });

  const { data: orgs } = useQuery({
    queryKey: [...qk.organizations, "pick"],
    queryFn: async () => {
      const supabase = createClient();
      const { data } = await supabase.from("organizations").select("id, name").order("name");
      return data ?? [];
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
      if (!res.ok) throw new Error(res.message);
    },
    onSuccess: () => {
      toast.success("Created");
      void invalidateAfterMutation(qc);
      form.reset();
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
        <h1 className="text-2xl font-semibold">Contacts</h1>
        <p className="text-sm text-muted-foreground">{contacts?.length ?? 0} contacts</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New contact</CardTitle>
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
                          <SelectValue placeholder="Organization" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="_">None</SelectItem>
                        {(orgs ?? []).map((o: { id: string; name: string }) => (
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
                      <Input {...field} value={field.value ?? ""} />
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
                Create
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Email</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(contacts ?? []).map((row: Record<string, unknown>) => (
              <TableRow key={String(row.id)}>
                <TableCell>
                  <Link href={`/contacts/${row.id}`} className="hover:underline">
                    {String(row.full_name ?? "—")}
                  </Link>
                </TableCell>
                <TableCell>
                  {(row.organizations as { name?: string } | null)?.name ?? "—"}
                </TableCell>
                <TableCell>{String(row.email ?? "—")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
