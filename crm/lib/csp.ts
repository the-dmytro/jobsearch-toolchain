/** Per-request nonce: 128 random bits, base64. */
export function createNonce(): string {
  return Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64");
}

export type CspOptions = {
  nonce: string;
  /**
   * Supabase project URL. Only its origin (scheme, host, port) is used. Omit it when no project is
   * configured: the policy then allows no Supabase origin.
   */
  supabaseUrl?: string;
  /** Adds 'unsafe-eval' (React development tooling). Never in production. */
  development: boolean;
  /** Adds upgrade-insecure-requests. Set only when the request itself is https. */
  upgradeInsecureRequests: boolean;
};

/** Websocket form of an http(s) origin, for connect-src. */
function toWebSocketOrigin(origin: string): string {
  return origin.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
}

/**
 * Content-Security-Policy for a page response. Single line so it is valid as a
 * header value.
 */
export function buildContentSecurityPolicy({
  nonce,
  supabaseUrl,
  development,
  upgradeInsecureRequests,
}: CspOptions): string {
  const supabaseOrigins = supabaseUrl ? [new URL(supabaseUrl).origin] : [];
  const scriptSrc = [
    "'self'",
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    ...(development ? ["'unsafe-eval'"] : []),
  ].join(" ");

  const directives = [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    ["img-src 'self' data: blob:", ...supabaseOrigins].join(" "),
    "font-src 'self' data:",
    ["connect-src 'self'", ...supabaseOrigins.flatMap((o) => [o, toWebSocketOrigin(o)])].join(" "),
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    ...(upgradeInsecureRequests ? ["upgrade-insecure-requests"] : []),
  ];

  return directives.join("; ");
}
