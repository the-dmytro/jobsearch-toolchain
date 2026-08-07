"use server";

import { revalidatePath } from "next/cache";
import { communicationInsertSchema } from "@/lib/schemas/communication";
import { createClient } from "@/lib/supabase/server";

export async function createCommunication(input: unknown) {
  const parsed = communicationInsertSchema.safeParse(input);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }
  const supabase = await createClient();
  const { error } = await supabase.from("communications").insert(parsed.data);
  if (error) return { error: error.message };
  if (parsed.data.application_id) {
    revalidatePath(`/applications/${parsed.data.application_id}`);
  }
  revalidatePath("/communications");
  return { ok: true as const };
}
