"use server";

import { revalidatePath } from "next/cache";
import { fail, GENERIC_FAILURE, invalidInput, logActionError } from "@/lib/actions/result";
import {
  applicationEventSchema,
  applicationUpdateSchema,
  stageChangeSchema,
} from "@/lib/schemas/application";
import { createClient } from "@/lib/supabase/server";
import type { ActionResult } from "@/lib/types/action-result";

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

/**
 * Moves an application to a new stage and records a stage_change event. If the event cannot
 * be written, the stage and status are restored to their previous values before returning.
 */
export async function changeApplicationStage(input: unknown): Promise<ActionResult> {
  const parsed = stageChangeSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  const { applicationId, newStage } = parsed.data;

  try {
    const supabase = await createClient();

    const { data: previous, error: readError } = await supabase
      .from("applications")
      .select("current_stage, status")
      .eq("id", applicationId)
      .single();
    if (readError || !previous) {
      logActionError("changeApplicationStage: read failed", readError ?? "no row");
      return fail("Could not find this application.");
    }

    const { error: updateError } = await supabase
      .from("applications")
      .update({ current_stage: newStage })
      .eq("id", applicationId);
    if (updateError) {
      logActionError("changeApplicationStage: update failed", updateError);
      return fail("Could not move the application. Try again.");
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
      const { error: revertError } = await supabase
        .from("applications")
        .update({ current_stage: previous.current_stage, status: previous.status })
        .eq("id", applicationId);
      if (revertError) {
        logActionError("changeApplicationStage: revert failed", revertError);
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
