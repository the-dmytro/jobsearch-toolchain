import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getUser = vi.fn();
let capturedCookieOptions: {
  cookies: { setAll: (cookies: { name: string; value: string; options?: object }[]) => void };
} | null = null;
vi.mock("@supabase/ssr", () => ({
  createServerClient: (_url: string, _key: string, options: unknown) => {
    capturedCookieOptions = options as typeof capturedCookieOptions;
    return { auth: { getUser, signOut: vi.fn() } };
  },
}));

import { config, proxy } from "@/proxy";

const SUPABASE = "https://abcd.supabase.co";

function request(path: string, headers: Record<string, string> = {}) {
  return new NextRequest(`http://localhost:3000${path}`, { headers });
}

describe("proxy", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", SUPABASE);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-test-value");
    vi.stubEnv("CRM_OWNER_EMAIL", "owner@example.com");
    getUser.mockReset();
  });

  it("applies the CSP header with the same nonce as the forwarded x-nonce header", async () => {
    getUser.mockResolvedValue({ data: { user: { email: "owner@example.com" } } });
    const res = await proxy(request("/applications"));

    const csp = res.headers.get("content-security-policy");
    expect(csp).toBeTruthy();
    const nonce = /'nonce-([^']+)'/.exec(csp ?? "")?.[1];
    expect(nonce).toBeTruthy();
    expect(res.headers.get("x-middleware-request-x-nonce")).toBe(nonce);
  });

  it("forwards refreshed Supabase cookies to the rendered request", async () => {
    getUser.mockImplementation(async () => {
      capturedCookieOptions?.cookies.setAll([
        { name: "sb-token", value: "fresh value", options: {} },
      ]);
      return { data: { user: { email: "owner@example.com" } } };
    });
    const res = await proxy(request("/applications", { cookie: "sb-token=stale" }));

    expect(res.headers.get("x-middleware-request-cookie")).toBe("sb-token=fresh value");
  });

  it("still sets the CSP header on the auth redirect for signed-out users", async () => {
    getUser.mockResolvedValue({ data: { user: null } });
    const res = await proxy(request("/applications"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
    expect(res.headers.get("content-security-policy")).toContain("script-src 'self' 'nonce-");
  });

  it("sets the CSP header on the forbidden redirect for non-owners", async () => {
    getUser.mockResolvedValue({ data: { user: { email: "someone@else.example" } } });
    const res = await proxy(request("/"));

    expect(res.headers.get("location")).toContain("error=forbidden");
    expect(res.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
  });

  it("matcher excludes static assets and image files", () => {
    const pattern = new RegExp(`^${(config.matcher[0] as string).replace(/^\//, "\\/")}$`);
    expect(pattern.test("/_next/static/chunks/app.js")).toBe(false);
    expect(pattern.test("/_next/image?url=x")).toBe(false);
    expect(pattern.test("/logo.svg")).toBe(false);
    expect(pattern.test("/applications")).toBe(true);
  });
});
