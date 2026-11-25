"use server";

import { revalidatePath } from "next/cache";
import { fail, GENERIC_FAILURE, invalidInput, logActionError } from "@/lib/actions/result";
import { communicationInsertSchema } from "@/lib/schemas/communication";
import { createClient } from "@/lib/supabase/server";
import type { ActionResult } from "@/lib/types/action-result";

export async function createCommunication(input: unknown): Promise<ActionResult> {
  const parsed = communicationInsertSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  try {
    const supabase = await createClient();
    const { error } = await supabase.from("communications").insert(parsed.data);
    if (error) {
      logActionError("createCommunication: insert failed", error);
      return fail("Could not save the communication. Try again.");
    }
    if (parsed.data.application_id) {
      revalidatePath(`/applications/${parsed.data.application_id}`);
    }
    revalidatePath("/communications");
    return { ok: true };
  } catch (error) {
    logActionError("createCommunication: unexpected error", error);
    return fail(GENERIC_FAILURE);
  }
}
