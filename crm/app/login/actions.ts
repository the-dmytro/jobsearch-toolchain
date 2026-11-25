"use server";

import { headers } from "next/headers";
import { resolveServerSiteUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

export type SendMagicLinkResult =
  | { ok: true }
  | { ok: false; message: string };

function formatAuthError(error: { message: string; code?: string }): string {
  const normalized = error.message.toLowerCase();

  if (
    error.code === "over_email_send_rate_limit" ||
    normalized.includes("email rate limit")
  ) {
    return "Too many sign-in emails were requested recently. Wait about an hour, then try again.";
  }

  if (
    error.code === "over_request_rate_limit" ||
    normalized.includes("rate limit")
  ) {
    return "Too many attempts. Wait a minute, then try again.";
  }

  return "We couldn't send the sign-in link. Check the address and try again.";
}

async function resolveAuthRedirectOrigin(): Promise<string> {
  const serverSiteUrl = resolveServerSiteUrl();
  if (
    !serverSiteUrl.includes("localhost") &&
    !serverSiteUrl.includes("127.0.0.1")
  ) {
    return serverSiteUrl;
  }

  const headerStore = await headers();
  const host =
    headerStore.get("x-forwarded-host")?.split(",")[0]?.trim() ??
    headerStore.get("host")?.trim();
  const protocol =
    headerStore.get("x-forwarded-proto")?.split(",")[0]?.trim() ?? "https";

  if (host) {
    return `${protocol}://${host}`.replace(/\/$/, "");
  }

  return resolveServerSiteUrl();
}

export async function sendMagicLink(email: string): Promise<SendMagicLinkResult> {
  const trimmed = email.trim().toLowerCase();

  if (!trimmed) {
    return { ok: false, message: "Enter your email address." };
  }

  if (
    !process.env.NEXT_PUBLIC_SUPABASE_URL ||
    !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  ) {
    return {
      ok: false,
      message: "Sign-in isn't set up on this site yet. Ask the site owner to finish setup.",
    };
  }

  const origin = await resolveAuthRedirectOrigin();
  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithOtp({
    email: trimmed,
    options: {
      emailRedirectTo: `${origin}/auth/callback`,
    },
  });

  if (error) {
    return { ok: false, message: formatAuthError(error) };
  }

  return { ok: true };
}
