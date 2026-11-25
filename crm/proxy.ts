import { NextResponse, type NextRequest } from "next/server";
import { EnvConfigError, getPublicEnv } from "@/lib/env";
import { buildContentSecurityPolicy, createNonce } from "@/lib/csp";
import { SECURITY_HEADERS } from "@/lib/security-headers";
import { updateSession } from "@/lib/supabase/session";

/**
 * Shown when required environment variables are missing or invalid. Plain text, no detail about
 * which variable: the name is in the server log, not in the response.
 */
const NOT_CONFIGURED_BODY = "The app is not configured yet.";

function notConfiguredResponse(request: NextRequest, nonce: string): NextResponse {
  const csp = buildContentSecurityPolicy({
    nonce,
    development: process.env.NODE_ENV === "development",
    upgradeInsecureRequests: request.nextUrl.protocol === "https:",
    vercelPreviewToolbar: process.env.VERCEL_ENV === "preview",
  });
  const response = new NextResponse(NOT_CONFIGURED_BODY, {
    status: 503,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
  for (const { key, value } of SECURITY_HEADERS) response.headers.set(key, value);
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const nonce = createNonce();
  let supabaseUrl: string;
  try {
    supabaseUrl = getPublicEnv().NEXT_PUBLIC_SUPABASE_URL;
  } catch (error) {
    if (error instanceof EnvConfigError) {
      console.error(`proxy: ${error.message}`);
      return notConfiguredResponse(request, nonce);
    }
    throw error;
  }
  const csp = buildContentSecurityPolicy({
    nonce,
    supabaseUrl,
    development: process.env.NODE_ENV === "development",
    upgradeInsecureRequests: request.nextUrl.protocol === "https:",
    vercelPreviewToolbar: process.env.VERCEL_ENV === "preview",
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

// Matchers must be literal strings so Next can analyse them at build time.
// Prefetches (next/link, router prefetch) skip the proxy, per the Next CSP guide.
export const config = {
  matcher: [
    {
      source:
        "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:ico|png|jpg|jpeg|gif|svg|webp|avif|woff|woff2|ttf|css|js|map|txt|xml|json|webmanifest)$).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
