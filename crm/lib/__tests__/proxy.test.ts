import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getUser: vi.fn(),
  signOut: vi.fn(),
  capturedOptions: null as null | {
    cookies: { setAll: (cookies: { name: string; value: string; options?: object }[]) => void };
  },
}));

vi.mock("@supabase/ssr", () => ({
  createServerClient: (_url: string, _key: string, options: unknown) => {
    mocks.capturedOptions = options as typeof mocks.capturedOptions;
    return { auth: { getUser: mocks.getUser, signOut: mocks.signOut } };
  },
}));

import { config, proxy } from "@/proxy";

const SUPABASE = "https://abcd.supabase.co";
const OWNER = { email: "owner@example.com" };

function request(path: string, headers: Record<string, string> = {}, base = "http://localhost:3000") {
  return new NextRequest(`${base}${path}`, { headers });
}

/** Regex form of the object matcher's source, anchored to the whole path. */
function matcherFor(source: string): RegExp {
  return new RegExp(`^${source}$`);
}

describe("proxy", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", SUPABASE);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-test-value");
    vi.stubEnv("CRM_OWNER_EMAIL", "owner@example.com");
    mocks.getUser.mockReset();
    mocks.signOut.mockReset();
    mocks.signOut.mockResolvedValue(undefined);
  });

  it("answers 503 with plain text, the CSP and the security headers when the environment is not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await proxy(request("/applications"));

    expect(res.status).toBe(503);
    expect(res.headers.get("content-type")).toBe("text/plain; charset=utf-8");
    expect(await res.text()).toBe("The app is not configured yet.");
    expect(res.headers.get("content-security-policy")).toContain("script-src 'self' 'nonce-");
    expect(res.headers.get("content-security-policy")).not.toContain("supabase.co");
    expect(res.headers.get("x-frame-options")).toBe("DENY");
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    expect(res.headers.get("strict-transport-security")).toContain("max-age=");
    expect(mocks.getUser).not.toHaveBeenCalled();
  });

  it("names the missing variable only in the server log, not in the response", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await proxy(request("/applications"));

    expect(await res.text()).not.toContain("NEXT_PUBLIC_SUPABASE_URL");
    expect(log).toHaveBeenCalledWith(expect.stringContaining("NEXT_PUBLIC_SUPABASE_URL"));
  });

  it("applies the CSP header with the same nonce as the forwarded x-nonce header", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: OWNER } });
    const res = await proxy(request("/applications"));

    const csp = res.headers.get("content-security-policy");
    const nonce = /'nonce-([^']+)'/.exec(csp ?? "")?.[1];
    expect(nonce).toBeTruthy();
    expect(res.headers.get("x-middleware-request-x-nonce")).toBe(nonce);
  });

  it("sends upgrade-insecure-requests only for https requests", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: OWNER } });

    const plain = await proxy(request("/applications"));
    expect(plain.headers.get("content-security-policy")).not.toContain("upgrade-insecure-requests");

    const secure = await proxy(request("/applications", {}, "https://crm.example.com"));
    expect(secure.headers.get("content-security-policy")).toContain("upgrade-insecure-requests");
  });

  it("forwards refreshed Supabase cookies, keeping other cookies and the original encoding", async () => {
    mocks.getUser.mockImplementation(async () => {
      mocks.capturedOptions?.cookies.setAll([
        { name: "sb-token", value: "base64-fresh%20value", options: {} },
      ]);
      return { data: { user: OWNER } };
    });
    const res = await proxy(
      request("/applications", { cookie: "sb-token=stale; theme=dark" })
    );

    expect(res.headers.get("x-middleware-request-cookie")).toBe(
      "theme=dark; sb-token=base64-fresh%20value"
    );
  });

  it("still sets the CSP header on the auth redirect for signed-out users", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null } });
    const res = await proxy(request("/applications"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
    expect(res.headers.get("content-security-policy")).toContain("script-src 'self' 'nonce-");
  });

  it("sets the CSP header on the forbidden redirect for non-owners", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { email: "someone@else.example" } } });
    const res = await proxy(request("/"));

    expect(res.headers.get("location")).toContain("error=forbidden");
    expect(res.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
  });

  it("carries clearing Supabase cookies onto the forbidden redirect", async () => {
    mocks.getUser.mockImplementation(async () => {
      mocks.capturedOptions?.cookies.setAll([
        { name: "sb-token", value: "", options: { path: "/", maxAge: 0 } },
      ]);
      return { data: { user: { email: "someone@else.example" } } };
    });
    const res = await proxy(request("/", { cookie: "sb-token=stale" }));

    expect(res.headers.get("location")).toContain("error=forbidden");
    expect(res.headers.getSetCookie().some((c) => c.startsWith("sb-token=;"))).toBe(true);
  });

  it("carries refreshed Supabase cookies onto the signed-out redirect", async () => {
    mocks.getUser.mockImplementation(async () => {
      mocks.capturedOptions?.cookies.setAll([
        { name: "sb-refresh", value: "rotated", options: { path: "/" } },
      ]);
      return { data: { user: null } };
    });
    const res = await proxy(request("/applications"));

    expect(res.headers.getSetCookie().some((c) => c.startsWith("sb-refresh=rotated"))).toBe(true);
  });

  describe("matcher", () => {
    const entry = config.matcher[0];

    it("is the object form with prefetch requests excluded", () => {
      expect(typeof entry).toBe("object");
      expect(entry.missing).toEqual([
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ]);
    });

    it.each([
      "/_next/static/chunks/app.js",
      "/_next/image?url=x",
      "/favicon.ico",
      "/logo.svg",
      "/photo.avif",
      "/fonts/inter.woff2",
      "/fonts/inter.ttf",
      "/styles/site.css",
      "/app.js",
      "/app.js.map",
      "/robots.txt",
      "/sitemap.xml",
      "/data/export.json",
      "/site.webmanifest",
    ])("excludes static asset %s", (path) => {
      expect(matcherFor(entry.source).test(path)).toBe(false);
    });

    it.each(["/", "/applications", "/applications/123", "/login", "/auth/callback"])(
      "includes application route %s",
      (path) => {
        expect(matcherFor(entry.source).test(path)).toBe(true);
      }
    );
  });
});
