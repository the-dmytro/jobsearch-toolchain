import { NextResponse, type NextRequest } from "next/server";
import { getPublicEnv } from "@/lib/env";
import { buildContentSecurityPolicy, createNonce } from "@/lib/csp";
import { updateSession } from "@/lib/supabase/session";

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const nonce = createNonce();
  const { NEXT_PUBLIC_SUPABASE_URL } = getPublicEnv();
  const csp = buildContentSecurityPolicy({
    nonce,
    supabaseUrl: NEXT_PUBLIC_SUPABASE_URL,
    development: process.env.NODE_ENV === "development",
    production: process.env.NODE_ENV === "production",
  });

  // Next.js reads the nonce from the request CSP header and applies it to its own
  // scripts; `x-nonce` is for app code (for example headers() in the root layout).
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = await updateSession(request, requestHeaders);
  // Applied to every response, including the auth redirects returned by updateSession.
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
