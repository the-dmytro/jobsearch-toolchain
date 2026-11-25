import { describe, expect, it } from "vitest";
import { safeExternalUrl } from "@/lib/safe-url";

describe("safeExternalUrl", () => {
  it("returns the normalized href for http and https", () => {
    expect(safeExternalUrl("https://example.com/jobs?id=1")).toBe(
      "https://example.com/jobs?id=1"
    );
    expect(safeExternalUrl("HTTP://Example.COM")).toBe("http://example.com/");
  });

  it("allows mailto links", () => {
    expect(safeExternalUrl("mailto:jobs@example.com")).toBe("mailto:jobs@example.com");
  });

  it("trims surrounding whitespace before parsing", () => {
    expect(safeExternalUrl("  https://example.com/a  ")).toBe("https://example.com/a");
  });

  it.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://example.com/file",
  ])("rejects unsafe scheme %s", (value) => {
    expect(safeExternalUrl(value)).toBeNull();
  });

  it("rejects relative, scheme-less and malformed values", () => {
    expect(safeExternalUrl("/applications/1")).toBeNull();
    expect(safeExternalUrl("example.com/jobs")).toBeNull();
    expect(safeExternalUrl("https://")).toBeNull();
    expect(safeExternalUrl("not a url")).toBeNull();
  });

  it("returns null for empty, blank and missing values", () => {
    expect(safeExternalUrl("")).toBeNull();
    expect(safeExternalUrl("   ")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
    expect(safeExternalUrl(undefined)).toBeNull();
  });
});
