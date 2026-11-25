import { describe, expect, it } from "vitest";
import { resolveAuthRedirectOrigin } from "@/lib/auth-redirect";

const site = "https://crm.example.com";

describe("resolveAuthRedirectOrigin", () => {
  it("returns to the production alias the form was submitted on", () => {
    expect(
      resolveAuthRedirectOrigin({
        forwardedHost: "crm-other-alias.vercel.app",
        forwardedProto: "https",
        siteUrl: site,
        onVercel: true,
      })
    ).toBe("https://crm-other-alias.vercel.app");
  });

  it("returns to a preview deployment on Vercel", () => {
    expect(
      resolveAuthRedirectOrigin({
        forwardedHost: "crm-abc123-team.vercel.app, proxy.internal",
        host: "ignored.example",
        siteUrl: site,
        onVercel: true,
      })
    ).toBe("https://crm-abc123-team.vercel.app");
  });

  it("keeps http for local development", () => {
    expect(
      resolveAuthRedirectOrigin({
        host: "localhost:3000",
        forwardedProto: "http",
        siteUrl: "http://localhost:3000",
        onVercel: false,
      })
    ).toBe("http://localhost:3000");
  });

  it("forces https for non-local hosts", () => {
    expect(
      resolveAuthRedirectOrigin({
        host: "crm.example.com",
        forwardedProto: "http",
        siteUrl: site,
        onVercel: false,
      })
    ).toBe("https://crm.example.com");
  });

  it("ignores an untrusted host when self-hosted", () => {
    expect(
      resolveAuthRedirectOrigin({
        forwardedHost: "attacker.example",
        siteUrl: site,
        onVercel: false,
      })
    ).toBe(site);
  });

  it("falls back to the site URL for a missing or malformed host", () => {
    expect(resolveAuthRedirectOrigin({ siteUrl: `${site}/`, onVercel: true })).toBe(site);
    expect(
      resolveAuthRedirectOrigin({ host: "evil.example/path?x", siteUrl: site, onVercel: true })
    ).toBe(site);
  });
});
