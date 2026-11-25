import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getPublicEnv, isAllowedOwnerEmail } from "@/lib/env";

type CookieToSet = { name: string; value: string; options?: object };

/**
 * Cookie header for the rendered request: the original header with only the names
 * that were refreshed replaced. Values are used exactly as @supabase/ssr supplies
 * them (already encoded); nothing is decoded or re-encoded. Cleared cookies (empty
 * value) are dropped.
 */
export function forwardedCookieHeader(
  originalCookieHeader: string,
  refreshed: Map<string, string>
): string {
  const kept = originalCookieHeader
    .split(";")
    .map((pair) => pair.trim())
    .filter((pair) => pair.length > 0)
    .filter((pair) => !refreshed.has(pair.split("=")[0].trim()));
  const set = [...refreshed]
    .filter(([, value]) => value !== "")
    .map(([name, value]) => `${name}=${value}`);
  return [...kept, ...set].join("; ");
}

/**
 * Refreshes the Supabase session cookies and enforces the owner allowlist.
 * `requestHeaders` lets the proxy forward extra request headers (for example the
 * CSP nonce) to the rendered page. Every response returned here, including the
 * auth redirects, carries the refreshed or cleared Supabase cookies.
 */
export async function updateSession(
  request: NextRequest,
  requestHeaders: Headers = new Headers(request.headers)
) {
  const env = getPublicEnv();
  const originalCookieHeader = request.headers.get("cookie") ?? "";
  const refreshed = new Map<string, string>();
  const responseCookies: CookieToSet[] = [];
  let supabaseResponse = NextResponse.next({ request: { headers: requestHeaders } });

  const supabase = createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            request.cookies.set(name, value);
            refreshed.set(name, value);
            responseCookies.push({ name, value, options });
          });
          const cookieHeader = forwardedCookieHeader(originalCookieHeader, refreshed);
          if (cookieHeader) {
            requestHeaders.set("cookie", cookieHeader);
          } else {
            requestHeaders.delete("cookie");
          }
          supabaseResponse = NextResponse.next({
            request: { headers: requestHeaders },
          });
        },
      },
    }
  );

  // Applies every cookie refreshed so far to a response (latest value wins per name).
  function withSessionCookies<T extends NextResponse>(response: T): T {
    for (const { name, value, options } of responseCookies) {
      response.cookies.set(name, value, options);
    }
    return response;
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isLogin = path.startsWith("/login");
  const isAuthRoute = path.startsWith("/auth");

  if (!user && !isLogin && !isAuthRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return withSessionCookies(NextResponse.redirect(url));
  }

  if (user && !isAllowedOwnerEmail(user.email)) {
    await supabase.auth.signOut();
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("error", "forbidden");
    return withSessionCookies(NextResponse.redirect(url));
  }

  if (user && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return withSessionCookies(NextResponse.redirect(url));
  }

  return withSessionCookies(supabaseResponse);
}
