"use server";

import { revalidatePath } from "next/cache";
import { fail, GENERIC_FAILURE, invalidInput, logActionError } from "@/lib/actions/result";
import { contactInsertSchema } from "@/lib/schemas/contact";
import { createClient } from "@/lib/supabase/server";
import type { ActionResult } from "@/lib/types/action-result";

export async function createContact(input: unknown): Promise<ActionResult<{ id: string }>> {
  const parsed = contactInsertSchema.safeParse(input);
  if (!parsed.success) return invalidInput(parsed.error);
  const payload = {
    ...parsed.data,
    email: parsed.data.email === "" ? null : parsed.data.email,
  };
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("contacts")
      .insert(payload)
      .select("id")
      .single();
    if (error || !data) {
      logActionError("createContact: insert failed", error ?? "no row returned");
      return fail("Could not save the contact. Try again.");
    }
    revalidatePath("/contacts");
    return { ok: true, data: { id: data.id } };
  } catch (error) {
    logActionError("createContact: unexpected error", error);
    return fail(GENERIC_FAILURE);
  }
}
