import { describe, expect, it } from "vitest";
import { isSafeStoragePath } from "@/lib/storage-path";

describe("isSafeStoragePath", () => {
  it.each([
    "transcripts/2026/call-1.pdf",
    "artifacts/cv_v2.pdf",
    "file..pdf",
    "a/b..c/d.pdf",
    "my file.pdf",
    "a".repeat(1024),
  ])("accepts relative object key %s", (path) => {
    expect(isSafeStoragePath(path)).toBe(true);
  });

  it.each([
    ["empty", ""],
    ["blank", "   "],
    ["leading slash", "/etc/passwd"],
    ["trailing slash", "a/"],
    ["doubled slash", "a//b"],
    ["dot segment", "./a.pdf"],
    ["inner dot segment", "a/./b.pdf"],
    ["parent segment", "../secrets.pdf"],
    ["embedded parent segment", "a/../../b.pdf"],
    ["trailing parent segment", "a/.."],
    ["backslash", "a\\b.pdf"],
    ["windows traversal", "..\\secrets.pdf"],
    ["percent-encoded traversal", "a%2e%2e/b.pdf"],
    ["encoded slash", "a%2Fb.pdf"],
    ["query marker", "a?b.pdf"],
    ["fragment marker", "a#b.pdf"],
    ["NUL byte", "a\0b.pdf"],
    ["unit separator", "a\x1fb.pdf"],
    ["DEL character", "a\x7fb.pdf"],
    ["newline", "a\nb.pdf"],
    ["leading tab", "\tfile.pdf"],
    ["trailing newline", "file.pdf\n"],
    ["leading space", " file.pdf"],
    ["trailing space", "file.pdf "],
    ["over the length limit", "a".repeat(1025)],
  ])("rejects %s", (_label, path) => {
    expect(isSafeStoragePath(path)).toBe(false);
  });
});
