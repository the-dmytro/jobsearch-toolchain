"use server";

import { revalidatePath } from "next/cache";
import { interviewInsertSchema } from "@/lib/schemas/interview";
import { createClient } from "@/lib/supabase/server";

export async function createInterview(input: unknown) {
  const parsed = interviewInsertSchema.safeParse(input);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("interviews")
    .insert(parsed.data)
    .select("id")
    .single();
  if (error) return { error: error.message };
  revalidatePath(`/applications/${parsed.data.application_id}`);
  revalidatePath("/interviews");
  return { ok: true as const, id: data.id };
}
