import "server-only";

import { createClient } from "@supabase/supabase-js";
import { getPublicEnv, getServerEnv } from "@/lib/env";
import type { Database } from "@/types/database.types";

/** Privileged client (service role). Storage signed URLs and admin-only operations. */
export function createAdminClient() {
  const { NEXT_PUBLIC_SUPABASE_URL: url } = getPublicEnv();
  const { serviceKey } = getServerEnv();
  return createClient<Database>(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
