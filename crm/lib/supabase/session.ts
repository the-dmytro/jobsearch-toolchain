import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getPublicEnv, isAllowedOwnerEmail } from "@/lib/env";

/**
 * Refreshes the Supabase session cookies and enforces the owner allowlist.
 * `requestHeaders` lets the proxy forward extra request headers (for example the
 * CSP nonce) to the rendered page; they are carried on every response.
 */
export async function updateSession(
  request: NextRequest,
  requestHeaders: Headers = new Headers(request.headers)
) {
  let supabaseResponse = NextResponse.next({ request: { headers: requestHeaders } });
  const env = getPublicEnv();

  const supabase = createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          // Keep the forwarded Cookie header in step with the refreshed cookies.
          // Raw values (not RequestCookies#toString, which percent-encodes).
          requestHeaders.set(
            "cookie",
            request.cookies
              .getAll()
              .map(({ name, value }) => `${name}=${value}`)
              .join("; ")
          );
          supabaseResponse = NextResponse.next({
            request: { headers: requestHeaders },
          });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

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
    return NextResponse.redirect(url);
  }

  if (user && !isAllowedOwnerEmail(user.email)) {
    await supabase.auth.signOut();
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("error", "forbidden");
    return NextResponse.redirect(url);
  }

  if (user && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
