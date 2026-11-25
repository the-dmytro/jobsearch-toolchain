/**
 * Security headers for every page response. `next.config.ts` applies them through `headers()`.
 * `proxy.ts` sets the same list on its own responses that Next does not wrap, such as the 503
 * for a missing configuration. Change them here, in one place.
 */
export const SECURITY_HEADERS: readonly { key: string; value: string }[] = [
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), browsing-topics=()",
  },
];
