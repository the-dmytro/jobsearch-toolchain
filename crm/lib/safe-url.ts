const SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

/**
 * Normalized href for user-supplied external links. Only http, https and mailto
 * are allowed; anything else (javascript:, data:, relative, malformed) returns null
 * so the caller can render plain text.
 */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (trimmed === "") return null;

  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (!SAFE_PROTOCOLS.has(url.protocol)) return null;
  return url.href;
}
