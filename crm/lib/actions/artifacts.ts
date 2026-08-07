"use server";

import { createAdminClient } from "@/lib/supabase/admin";

export async function getArtifactSignedUrl(storagePath: string, bucket?: string) {
  try {
    const admin = createAdminClient();
    const b = bucket ?? process.env.SUPABASE_STORAGE_BUCKET ?? "job-artifacts";
    const { data, error } = await admin.storage.from(b).createSignedUrl(storagePath, 3600);
    if (error) return { error: error.message };
    return { url: data.signedUrl };
  } catch (e) {
    return {
      error: e instanceof Error ? e.message : "Missing SUPABASE_SERVICE_ROLE_KEY on server",
    };
  }
}
