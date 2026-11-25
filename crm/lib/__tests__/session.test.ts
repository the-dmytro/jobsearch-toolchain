import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getUser: vi.fn(),
  signOut: vi.fn(),
  capturedOptions: null as null | {
    cookies: {
      setAll: (
        cookies: { name: string; value: string; options?: object }[],
        headers: Record<string, string>
      ) => void;
    };
  },
}));

vi.mock("@supabase/ssr", () => ({
  createServerClient: (_url: string, _key: string, options: unknown) => {
    mocks.capturedOptions = options as typeof mocks.capturedOptions;
    return { auth: { getUser: mocks.getUser, signOut: mocks.signOut } };
  },
}));

import { updateSession } from "@/lib/supabase/session";

const OWNER = { email: "owner@example.com" };
const CACHE_HEADERS = {
  "Cache-Control": "private, no-cache, no-store, must-revalidate, max-age=0",
  Expires: "0",
  Pragma: "no-cache",
};

function request(path: string, headers: Record<string, string> = {}) {
  return new NextRequest(`http://localhost:3000${path}`, { headers });
}

/** Simulates @supabase/ssr refreshing a cookie during getUser(), with its cache headers. */
function refreshDuringGetUser(user: { email: string } | null) {
  mocks.getUser.mockImplementation(async () => {
    mocks.capturedOptions?.cookies.setAll(
      [{ name: "sb-token", value: "fresh", options: { path: "/" } }],
      CACHE_HEADERS
    );
    return { data: { user } };
  });
}

describe("updateSession cache headers", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://abcd.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-test-value");
    vi.stubEnv("CRM_OWNER_EMAIL", "owner@example.com");
    mocks.getUser.mockReset();
    mocks.signOut.mockReset();
    mocks.signOut.mockResolvedValue(undefined);
  });

  it("applies the cache headers to the rendered response for a signed-in owner", async () => {
    refreshDuringGetUser(OWNER);

    const res = await updateSession(request("/applications"));

    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe(CACHE_HEADERS["Cache-Control"]);
    expect(res.headers.get("expires")).toBe("0");
    expect(res.headers.get("pragma")).toBe("no-cache");
  });

  it("applies the cache headers to the signed-out login redirect", async () => {
    refreshDuringGetUser(null);

    const res = await updateSession(request("/applications"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
    expect(res.headers.get("cache-control")).toBe(CACHE_HEADERS["Cache-Control"]);
    expect(res.headers.get("pragma")).toBe("no-cache");
  });

  it("applies the cache headers to the forbidden redirect for a non-owner", async () => {
    refreshDuringGetUser({ email: "someone@else.example" });

    const res = await updateSession(request("/"));

    expect(res.headers.get("location")).toContain("error=forbidden");
    expect(res.headers.get("cache-control")).toBe(CACHE_HEADERS["Cache-Control"]);
    expect(res.headers.get("expires")).toBe("0");
  });

  it("applies the cache headers to the signed-in redirect away from the login page", async () => {
    refreshDuringGetUser(OWNER);

    const res = await updateSession(request("/login"));

    expect(res.headers.get("location")).toBe("http://localhost:3000/");
    expect(res.headers.get("cache-control")).toBe(CACHE_HEADERS["Cache-Control"]);
  });

  it("sets no cache headers when Supabase refreshed no cookies", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: OWNER } });

    const res = await updateSession(request("/applications"));

    expect(res.headers.get("cache-control")).toBeNull();
    expect(res.headers.get("pragma")).toBeNull();
  });
});
