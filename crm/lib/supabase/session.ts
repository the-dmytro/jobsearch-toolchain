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
  // Cache headers from @supabase/ssr (Cache-Control, Expires, Pragma) for auth cookie writes.
  const responseHeaders: Record<string, string> = {};
  let supabaseResponse = NextResponse.next({ request: { headers: requestHeaders } });

  const supabase = createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          Object.assign(responseHeaders, headers);
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

  // Applies every cookie refreshed so far, and the cache headers that came with them, to a
  // response. The latest value wins per name. Used for every response this function returns.
  function withSessionResponse<T extends NextResponse>(response: T): T {
    for (const { name, value, options } of responseCookies) {
      response.cookies.set(name, value, options);
    }
    for (const [key, value] of Object.entries(responseHeaders)) {
      response.headers.set(key, value);
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
    return withSessionResponse(NextResponse.redirect(url));
  }

  if (user && !isAllowedOwnerEmail(user.email)) {
    await supabase.auth.signOut();
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("error", "forbidden");
    return withSessionResponse(NextResponse.redirect(url));
  }

  if (user && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return withSessionResponse(NextResponse.redirect(url));
  }

  return withSessionResponse(supabaseResponse);
}
