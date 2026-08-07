"use server";

import { revalidatePath } from "next/cache";
import {
  applicationEventSchema,
  applicationUpdateSchema,
  stageChangeSchema,
} from "@/lib/schemas/application";
import { createClient } from "@/lib/supabase/server";

export async function updateApplication(input: unknown) {
  const parsed = applicationUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors as Record<string, string[]> };
  }
  const supabase = await createClient();
  const { id, ...patch } = parsed.data;
  const { error } = await supabase.from("applications").update(patch).eq("id", id);
  if (error) return { error: error.message };
  revalidatePath("/applications");
  revalidatePath(`/applications/${id}`);
  revalidatePath("/");
  return { ok: true as const };
}

export async function changeApplicationStage(input: unknown) {
  const parsed = stageChangeSchema.safeParse(input);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }
  const supabase = await createClient();
  const { applicationId, newStage } = parsed.data;
  const { error: uErr } = await supabase
    .from("applications")
    .update({ current_stage: newStage })
    .eq("id", applicationId);
  if (uErr) return { error: uErr.message };
  const { error: eErr } = await supabase.from("application_events").insert({
    application_id: applicationId,
    event_type: "stage_change",
    title: `Stage → ${newStage}`,
    event_at: new Date().toISOString(),
  });
  if (eErr) return { error: eErr.message };
  revalidatePath("/applications");
  revalidatePath(`/applications/${applicationId}`);
  revalidatePath("/");
  return { ok: true as const };
}

export async function logApplicationEvent(input: unknown) {
  const parsed = applicationEventSchema.safeParse(input);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }
  const supabase = await createClient();
  const { error } = await supabase.from("application_events").insert({
    application_id: parsed.data.applicationId,
    event_type: parsed.data.eventType,
    title: parsed.data.title ?? null,
    description: parsed.data.description ?? null,
    event_at: parsed.data.eventAt ?? new Date().toISOString(),
  });
  if (error) return { error: error.message };
  revalidatePath(`/applications/${parsed.data.applicationId}`);
  revalidatePath("/");
  return { ok: true as const };
}
