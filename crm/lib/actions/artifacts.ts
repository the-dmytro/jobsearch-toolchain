"use server";

import { isAllowedOwnerEmail, getServerEnv } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";
import { isSafeStoragePath } from "@/lib/storage-path";
import { createClient } from "@/lib/supabase/server";

export type ArtifactSignedUrlResult =
  | { ok: true; url: string }
  | { ok: false; message: string };

/** Short-lived: the link is opened immediately from the browser. */
const SIGNED_URL_TTL_SECONDS = 60;

const GENERIC_FAILURE = "Could not open the file. Try again.";

/**
 * Signed URL for a stored artifact. The bucket is always the server default from
 * env; callers cannot choose it. Only signed-in owners receive a URL.
 */
export async function getArtifactSignedUrl(
  storagePath: string
): Promise<ArtifactSignedUrlResult> {
  if (!isSafeStoragePath(storagePath)) {
    return { ok: false, message: "This file path is not valid." };
  }

  try {
    const supabase = await createClient();
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      return { ok: false, message: "Sign in to open this file." };
    }
    if (!isAllowedOwnerEmail(user.email)) {
      return { ok: false, message: "You do not have access to this file." };
    }

    const { storageBucket } = getServerEnv();
    const admin = createAdminClient();
    const { data, error } = await admin.storage
      .from(storageBucket)
      .createSignedUrl(storagePath, SIGNED_URL_TTL_SECONDS);

    if (error || !data?.signedUrl) {
      console.error("getArtifactSignedUrl: storage error", error?.message ?? "no url");
      return { ok: false, message: GENERIC_FAILURE };
    }
    return { ok: true, url: data.signedUrl };
  } catch (e) {
    console.error(
      "getArtifactSignedUrl: failed",
      e instanceof Error ? e.message : "unknown error"
    );
    return { ok: false, message: GENERIC_FAILURE };
  }
}
