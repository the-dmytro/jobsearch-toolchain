"use server";

import { getServerEnv, isAllowedOwnerEmail } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";
import { isSafeStoragePath } from "@/lib/storage-path";

export type ArtifactSignedUrlResult =
  | { ok: true; url: string }
  | { ok: false; message: string };

/** Short-lived: the link is opened immediately from the browser. */
const SIGNED_URL_TTL_SECONDS = 60;

const GENERIC_FAILURE = "Could not open the file. Try again.";

/**
 * Signed URL for an artifact the signed-in owner can see.
 *
 * Order matters: validate the path, require a signed-in owner, then look the path up
 * in `artifacts` with the user-scoped (RLS) client. A URL is signed only when a row
 * exists, and only in the server's default bucket.
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

    const { data: rows, error: lookupError } = await supabase
      .from("artifacts")
      .select("storage_bucket")
      .eq("storage_path", storagePath)
      .limit(1);

    if (lookupError) {
      console.error("getArtifactSignedUrl: lookup error", lookupError.message);
      return { ok: false, message: GENERIC_FAILURE };
    }
    const row = rows?.[0];
    if (!row) {
      return { ok: false, message: "File not found." };
    }

    // A row without a bucket means the default bucket; any other bucket is refused.
    const { storageBucket } = getServerEnv();
    if ((row.storage_bucket ?? storageBucket) !== storageBucket) {
      console.error("getArtifactSignedUrl: artifact bucket is not the server default");
      return { ok: false, message: GENERIC_FAILURE };
    }

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
