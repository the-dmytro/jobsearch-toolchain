"use server";

import { revalidatePath } from "next/cache";
import { fail, GENERIC_FAILURE, invalidInput, logActionError } from "@/lib/actions/result";
import { interviewInsertSchema } from "@/lib/schemas/interview";
import { createClient } from "@/lib/supabase/server";
import type { ActionResult } from "@/lib/types/action-result";

export async function createInterview(input: unknown): Promise<ActionResult<{ id: string }>> {
  const parsed = interviewInsertSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("interviews")
      .insert(parsed.data)
      .select("id")
      .single();
    if (error || !data) {
      logActionError("createInterview: insert failed", error ?? "no row returned");
      return fail("Could not schedule the interview. Try again.");
    }
    revalidatePath(`/applications/${parsed.data.application_id}`);
    revalidatePath("/interviews");
    return { ok: true, data: { id: data.id } };
  } catch (error) {
    logActionError("createInterview: unexpected error", error);
    return fail(GENERIC_FAILURE);
  }
}
