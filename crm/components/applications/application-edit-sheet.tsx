"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
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
import { mutationMessage, unwrapAction } from "@/components/applications/action-error";
import { OUTCOME_LABELS } from "@/components/applications/application-model";
import { changeApplicationStage, updateApplication } from "@/lib/actions/applications";
import { invalidateAfterMutation } from "@/lib/mutations";
import { applicationUpdateSchema } from "@/lib/schemas/application";
import {
  applicationOutcome,
  CANONICAL_STAGES,
  type CanonicalStage,
} from "@/lib/stages";
import type { Tables } from "@/types/database.types";

type FormValues = z.infer<typeof applicationUpdateSchema>;
type EditableField = Exclude<keyof FormValues, "id">;
type Patch = Partial<Record<EditableField, string | null>>;

const EDITABLE_FIELDS: readonly EditableField[] = [
  "applied_at",
  "salary_requested_text",
  "decline_reason",
  "notes",
];

/**
 * The partial payload for a save: only the fields the user changed. An emptied text field
 * is sent as null, so the database keeps no empty strings.
 */
export function changedValues(
  values: FormValues,
  dirty: Partial<Record<keyof FormValues, boolean | undefined>>
): Patch {
  const patch: Patch = {};
  for (const field of EDITABLE_FIELDS) {
    if (!dirty[field]) continue;
    const value = values[field];
    patch[field] = value === undefined || value === "" ? null : value;
  }
  return patch;
}

function isCanonicalStage(value: string): value is CanonicalStage {
  return (CANONICAL_STAGES as readonly string[]).includes(value);
}

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
  // Memoized: react-hook-form resets the form whenever the `values` object changes identity, so an
  // inline object would wipe what the user is typing on every render.
  const saved = useMemo<FormValues>(
    () => ({
      id: application.id,
      notes: application.notes,
      applied_at: application.applied_at,
      decline_reason: application.decline_reason,
      salary_requested_text: application.salary_requested_text,
    }),
    [application]
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(applicationUpdateSchema),
    values: saved,
  });
  const { dirtyFields } = form.formState;

  // Saves the changed non-stage fields only. Nothing is sent when no field changed.
  const saveMutation = useMutation({
    mutationFn: async (patch: Patch) => {
      if (Object.keys(patch).length === 0) return;
      const res = await updateApplication({ id: application.id, ...patch });
      unwrapAction(res);
    },
    onSuccess: async () => {
      toast.success("Saved");
      await invalidateAfterMutation(qc, { applicationId: application.id });
      onOpenChange(false);
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  // The stage moves through changeApplicationStage, which writes status and outcome with it and
  // records the event. While it runs, the control shows the stage being set. Once it settles, the
  // value comes from the refreshed application. "changed elsewhere" arrives as a friendly message.
  const stageMutation = useMutation({
    mutationFn: async (newStage: CanonicalStage) => {
      const res = await changeApplicationStage({ applicationId: application.id, newStage });
      unwrapAction(res);
    },
    onSuccess: async () => {
      toast.success("Stage updated");
      await invalidateAfterMutation(qc, { applicationId: application.id });
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  const stageValue = stageMutation.isPending
    ? stageMutation.variables
    : (application.current_stage ?? undefined);
  const outcomeLabel = OUTCOME_LABELS[applicationOutcome(application)];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Edit application</SheetTitle>
          <SheetDescription>Changes are saved to this application.</SheetDescription>
        </SheetHeader>

        <div className="mt-6 flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium leading-none">Stage</span>
            <Select
              value={stageValue ?? ""}
              disabled={stageMutation.isPending}
              onValueChange={(next) => {
                if (next === null || !isCanonicalStage(next) || next === application.current_stage) return;
                stageMutation.mutate(next);
              }}
            >
              <SelectTrigger aria-label="Stage">
                <SelectValue placeholder="Stage" />
              </SelectTrigger>
              <SelectContent>
                {CANONICAL_STAGES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Outcome: <span className="font-medium text-foreground">{outcomeLabel}</span>. Set by
              the stage.
            </p>
          </div>

          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((values) =>
                saveMutation.mutate(changedValues(values, dirtyFields))
              )}
              className="flex flex-col gap-4"
            >
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
              <Button type="submit" disabled={saveMutation.isPending || stageMutation.isPending}>
                Save
              </Button>
            </form>
          </Form>
        </div>
      </SheetContent>
    </Sheet>
  );
}
