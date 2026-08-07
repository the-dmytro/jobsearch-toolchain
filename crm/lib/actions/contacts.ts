"use server";

import { revalidatePath } from "next/cache";
import { contactInsertSchema } from "@/lib/schemas/contact";
import { createClient } from "@/lib/supabase/server";

export async function createContact(input: unknown) {
  const parsed = contactInsertSchema.safeParse(input);
  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }
  const payload = {
    ...parsed.data,
    email: parsed.data.email === "" ? null : parsed.data.email,
  };
  const supabase = await createClient();
  const { data, error } = await supabase.from("contacts").insert(payload).select("id").single();
  if (error) return { error: error.message };
  revalidatePath("/contacts");
  return { ok: true as const, id: data.id };
}
