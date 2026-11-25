import { describe, expect, it } from "vitest";
import { buildContentSecurityPolicy, createNonce } from "@/lib/csp";

const SUPABASE = "https://abcd.supabase.co";

function base(overrides: Partial<Parameters<typeof buildContentSecurityPolicy>[0]> = {}) {
  return buildContentSecurityPolicy({
    nonce: "abc123",
    supabaseUrl: SUPABASE,
    development: false,
    upgradeInsecureRequests: false,
    ...overrides,
  });
}

function directive(policy: string, name: string): string | undefined {
  return policy.split("; ").find((d) => d === name || d.startsWith(`${name} `));
}

describe("createNonce", () => {
  it("returns distinct base64 values of 16 random bytes", () => {
    const a = createNonce();
    const b = createNonce();
    expect(a).not.toBe(b);
    expect(Buffer.from(a, "base64")).toHaveLength(16);
  });
});

describe("buildContentSecurityPolicy", () => {
  it("uses a nonce and strict-dynamic, with no unsafe-eval outside development", () => {
    const csp = base();
    expect(directive(csp, "script-src")).toBe(
      "script-src 'self' 'nonce-abc123' 'strict-dynamic'"
    );
    expect(csp).not.toContain("unsafe-eval");
  });

  it("adds unsafe-eval only in development", () => {
    expect(directive(base({ development: true }), "script-src")).toContain("'unsafe-eval'");
    expect(base({ development: false })).not.toContain("unsafe-eval");
  });

  it("adds upgrade-insecure-requests only when the request is https", () => {
    expect(base({ upgradeInsecureRequests: true })).toContain("upgrade-insecure-requests");
    expect(base({ upgradeInsecureRequests: false })).not.toContain("upgrade-insecure-requests");
  });

  it("uses only the origin of a Supabase URL that has a port and a path", () => {
    const csp = base({ supabaseUrl: "https://abcd.supabase.co:8443/rest/v1/?x=1" });
    expect(directive(csp, "img-src")).toBe(
      "img-src 'self' data: blob: https://abcd.supabase.co:8443"
    );
    expect(directive(csp, "connect-src")).toBe(
      "connect-src 'self' https://abcd.supabase.co:8443 wss://abcd.supabase.co:8443"
    );
    expect(csp).not.toContain("/rest/v1");
  });

  it("allows the Supabase origin for images and websocket connections", () => {
    const csp = base({ supabaseUrl: `${SUPABASE}/` });
    expect(directive(csp, "img-src")).toBe(`img-src 'self' data: blob: ${SUPABASE}`);
    expect(directive(csp, "connect-src")).toBe(
      `connect-src 'self' ${SUPABASE} wss://abcd.supabase.co`
    );
  });

  it("includes the hardening directives and is a single line", () => {
    const csp = base({ upgradeInsecureRequests: true });
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
    expect(csp).toContain("font-src 'self' data:");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toMatch(/[\r\n]/);
  });
});
