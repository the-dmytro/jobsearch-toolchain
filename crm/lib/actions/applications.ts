"use server";

import { revalidatePath } from "next/cache";
import { fail, GENERIC_FAILURE, invalidInput, logActionError } from "@/lib/actions/result";
import {
  applicationEventSchema,
  applicationUpdateSchema,
  stageChangeSchema,
} from "@/lib/schemas/application";
import { createClient } from "@/lib/supabase/server";
import { statusAndOutcomeForStage } from "@/lib/stages";
import type { ActionResult } from "@/lib/types/action-result";

/** Shown when the row no longer holds the stage the board last read. */
const CHANGED_ELSEWHERE_MESSAGE = "This application changed elsewhere. Refresh and try again.";

function revalidateApplication(applicationId: string) {
  revalidatePath("/applications");
  revalidatePath(`/applications/${applicationId}`);
  revalidatePath("/");
}

export async function updateApplication(input: unknown): Promise<ActionResult> {
  const parsed = applicationUpdateSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  try {
    const supabase = await createClient();
    const { id, ...patch } = parsed.data;
    const { error } = await supabase.from("applications").update(patch).eq("id", id);
    if (error) {
      logActionError("updateApplication: update failed", error);
      return fail("Could not save the application. Try again.");
    }
    revalidateApplication(id);
    return { ok: true };
  } catch (error) {
    logActionError("updateApplication: unexpected error", error);
    return fail(GENERIC_FAILURE);
  }
}

type StageFields = {
  current_stage: string | null;
  status: string;
  outcome: string | null;
};

/**
 * Writes stage fields only where the row still holds `expectedStage`. Returns how many rows
 * changed: 0 means another writer moved the application first.
 */
async function writeIfStageIs(
  supabase: Awaited<ReturnType<typeof createClient>>,
  applicationId: string,
  expectedStage: string | null,
  fields: StageFields
): Promise<{ changed: number; error: { message: string } | null }> {
  const base = supabase.from("applications").update(fields).eq("id", applicationId);
  const guarded =
    expectedStage === null ? base.is("current_stage", null) : base.eq("current_stage", expectedStage);
  const { data, error } = await guarded.select("id");
  return { changed: data?.length ?? 0, error };
}

/**
 * Moves an application to a new stage and records a stage_change event. Stage, status and outcome
 * are written together, so leaving Closed clears the rejection. The write is conditional on the
 * stage the caller last read. If the event cannot be written, the previous values are restored
 * under the same condition.
 */
export async function changeApplicationStage(input: unknown): Promise<ActionResult> {
  const parsed = stageChangeSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  const { applicationId, newStage } = parsed.data;

  try {
    const supabase = await createClient();

    const { data: previous, error: readError } = await supabase
      .from("applications")
      .select("current_stage, status, outcome")
      .eq("id", applicationId)
      .single();
    if (readError || !previous) {
      logActionError("changeApplicationStage: read failed", readError ?? "no row");
      return fail("Could not find this application.");
    }

    const next = statusAndOutcomeForStage(newStage);
    const moved = await writeIfStageIs(supabase, applicationId, previous.current_stage, {
      current_stage: newStage,
      status: next.status,
      outcome: next.outcome,
    });
    if (moved.error) {
      logActionError("changeApplicationStage: update failed", moved.error);
      return fail("Could not move the application. Try again.");
    }
    if (moved.changed === 0) {
      return fail(CHANGED_ELSEWHERE_MESSAGE);
    }

    const { error: eventError } = await supabase.from("application_events").insert({
      application_id: applicationId,
      event_type: "stage_change",
      title: `Stage → ${newStage}`,
      event_at: new Date().toISOString(),
      metadata: { from_stage: previous.current_stage, to_stage: newStage },
    });
    if (eventError) {
      logActionError("changeApplicationStage: event insert failed, reverting", eventError);
      const reverted = await writeIfStageIs(supabase, applicationId, newStage, {
        current_stage: previous.current_stage,
        status: previous.status,
        outcome: previous.outcome,
      });
      if (reverted.error || reverted.changed === 0) {
        logActionError("changeApplicationStage: revert failed", reverted.error ?? "stage changed");
        return fail(
          "The stage change could not be recorded or undone. Refresh and check the stage."
        );
      }
      return fail("The stage change could not be recorded, so the stage was left unchanged. Try again.");
    }

    revalidateApplication(applicationId);
    return { ok: true };
  } catch (error) {
    logActionError("changeApplicationStage: unexpected error", error);
    return fail(GENERIC_FAILURE);
  }
}

export async function logApplicationEvent(input: unknown): Promise<ActionResult> {
  const parsed = applicationEventSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  try {
    const supabase = await createClient();
    const { error } = await supabase.from("application_events").insert({
      application_id: parsed.data.applicationId,
      event_type: parsed.data.eventType,
      title: parsed.data.title ?? null,
      description: parsed.data.description ?? null,
      event_at: parsed.data.eventAt ?? new Date().toISOString(),
    });
    if (error) {
      logActionError("logApplicationEvent: insert failed", error);
      return fail("Could not save the event. Try again.");
    }
    revalidatePath(`/applications/${parsed.data.applicationId}`);
    revalidatePath("/");
    return { ok: true };
  } catch (error) {
    logActionError("logApplicationEvent: unexpected error", error);
    return fail(GENERIC_FAILURE);
  }
}
