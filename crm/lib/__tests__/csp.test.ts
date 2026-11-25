import { describe, expect, it } from "vitest";
import { buildContentSecurityPolicy, createNonce } from "@/lib/csp";

const SUPABASE = "https://abcd.supabase.co";

function directive(policy: string, name: string): string | undefined {
  return policy.split("; ").find((d) => d.startsWith(`${name} `) || d === name);
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
  it("sets nonce-based script policy and no unsafe-eval in production", () => {
    const csp = buildContentSecurityPolicy({
      nonce: "abc123",
      supabaseUrl: SUPABASE,
      development: false,
      production: true,
    });
    expect(directive(csp, "script-src")).toBe(
      "script-src 'self' 'nonce-abc123' 'strict-dynamic'"
    );
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("upgrade-insecure-requests");
  });

  it("adds unsafe-eval only in development and omits upgrade-insecure-requests", () => {
    const csp = buildContentSecurityPolicy({
      nonce: "abc123",
      supabaseUrl: SUPABASE,
      development: true,
      production: false,
    });
    expect(directive(csp, "script-src")).toContain("'unsafe-eval'");
    expect(csp).not.toContain("upgrade-insecure-requests");
  });

  it("allows the Supabase origin for images and connections, including websockets", () => {
    const csp = buildContentSecurityPolicy({
      nonce: "n",
      supabaseUrl: `${SUPABASE}/`,
      development: false,
      production: true,
    });
    expect(directive(csp, "img-src")).toBe(
      `img-src 'self' data: blob: ${SUPABASE}`
    );
    expect(directive(csp, "connect-src")).toBe(
      `connect-src 'self' ${SUPABASE} wss://abcd.supabase.co`
    );
  });

  it("includes the hardening directives and is a single line", () => {
    const csp = buildContentSecurityPolicy({
      nonce: "n",
      supabaseUrl: SUPABASE,
      development: false,
      production: true,
    });
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
