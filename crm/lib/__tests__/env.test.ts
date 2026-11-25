import { afterEach, describe, expect, it, vi } from "vitest";
import { getPublicEnv, getServerEnv, isAllowedOwnerEmail } from "@/lib/env";

describe("getPublicEnv", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("names the missing variable without echoing any value", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "super-secret-anon-value");
    let message = "";
    try {
      getPublicEnv();
    } catch (e) {
      message = e instanceof Error ? e.message : String(e);
    }
    expect(message).toContain("NEXT_PUBLIC_SUPABASE_URL");
    expect(message).not.toContain("NEXT_PUBLIC_SUPABASE_ANON_KEY");
    expect(message).not.toContain("super-secret-anon-value");
  });

  it("returns parsed values and treats empty optional values as absent", () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://abcd.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "");
    const env = getPublicEnv();
    expect(env.NEXT_PUBLIC_SUPABASE_URL).toBe("https://abcd.supabase.co");
    expect(env.NEXT_PUBLIC_SITE_URL).toBeUndefined();
  });
});

describe("getServerEnv", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("requires a service key and defaults the storage bucket", () => {
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "");
    vi.stubEnv("SUPABASE_SECRET_KEY", "");
    vi.stubEnv("SUPABASE_STORAGE_BUCKET", "");
    expect(() => getServerEnv()).toThrow(/SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY/);

    vi.stubEnv("SUPABASE_SECRET_KEY", "fallback-key");
    expect(getServerEnv()).toMatchObject({ serviceKey: "fallback-key", storageBucket: "job-artifacts" });
  });
});

describe("isAllowedOwnerEmail", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("matches the configured owner list case-insensitively", () => {
    vi.stubEnv("CRM_OWNER_EMAIL", "Owner@Example.com, other@example.com");
    expect(isAllowedOwnerEmail("owner@example.com")).toBe(true);
    expect(isAllowedOwnerEmail("stranger@example.com")).toBe(false);
  });

  it("denies everyone in production when no owner is configured", () => {
    vi.stubEnv("CRM_OWNER_EMAIL", "");
    vi.stubEnv("NODE_ENV", "production");
    expect(isAllowedOwnerEmail("owner@example.com")).toBe(false);
  });
});
