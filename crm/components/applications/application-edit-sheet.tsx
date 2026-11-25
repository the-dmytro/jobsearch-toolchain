"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { updateApplication } from "@/lib/actions/applications";
import { invalidateAfterMutation } from "@/lib/mutations";
import { applicationUpdateSchema } from "@/lib/schemas/application";
import { CANONICAL_STAGES } from "@/lib/stages";
import type { Tables } from "@/types/database.types";
import { z } from "zod";

const formSchema = applicationUpdateSchema;

type FormValues = z.infer<typeof formSchema>;

export function ApplicationEditSheet({
  application,
  open,
  onOpenChange,
}: {
  application: Tables<"applications">;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    values: {
      id: application.id,
      status: application.status,
      current_stage: application.current_stage,
      notes: application.notes,
      applied_at: application.applied_at,
      decline_reason: application.decline_reason,
      outcome: application.outcome,
      salary_requested_text: application.salary_requested_text,
    },
  });

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const res = await updateApplication(values);
      if (!res.ok) throw new Error(res.message);
    },
    onSuccess: () => {
      toast.success("Saved");
      void invalidateAfterMutation(qc, { applicationId: application.id });
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Edit application</SheetTitle>
          <SheetDescription>Updates sync to Supabase via server action.</SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
            className="mt-6 flex flex-col gap-4"
          >
            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Status</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="current_stage"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Stage</FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value ?? ""}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Stage" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {CANONICAL_STAGES.map((s) => (
                        <SelectItem key={s} value={s}>
                          {s.replace(/_/g, " ")}
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
              name="applied_at"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Applied at (date)</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="salary_requested_text"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Salary requested</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="outcome"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Outcome</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="decline_reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Decline reason</FormLabel>
                  <FormControl>
                    <Textarea {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notes</FormLabel>
                  <FormControl>
                    <Textarea {...field} value={field.value ?? ""} rows={5} />
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
      </SheetContent>
    </Sheet>
  );
}
