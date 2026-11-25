import { describe, expect, it } from "vitest";
import { isSafeStoragePath } from "@/lib/storage-path";

describe("isSafeStoragePath", () => {
  it.each([
    "transcripts/2026/call-1.pdf",
    "artifacts/cv_v2.pdf",
  ])("accepts relative object key %s", (path) => {
    expect(isSafeStoragePath(path)).toBe(true);
  });

  it.each([
    ["empty", ""],
    ["blank", "   "],
    ["leading slash", "/etc/passwd"],
    ["parent traversal", "../secrets.pdf"],
    ["embedded traversal", "a/../../b.pdf"],
    ["double dot in name", "file..pdf"],
    ["backslash", "a\\b.pdf"],
    ["NUL byte", "a\0b.pdf"],
  ])("rejects %s", (_label, path) => {
    expect(isSafeStoragePath(path)).toBe(false);
  });
});
