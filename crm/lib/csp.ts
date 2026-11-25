/** Per-request nonce: 128 random bits, base64. */
export function createNonce(): string {
  return Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64");
}

export type CspOptions = {
  nonce: string;
  supabaseUrl: string;
  development: boolean;
  production: boolean;
};

/** Returns the websocket form of an https origin, for connect-src. */
function toWebSocketOrigin(origin: string): string {
  return origin.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
}

/**
 * Content-Security-Policy for every page response. Single line so it is valid as
 * a header value. `upgrade-insecure-requests` is production only.
 */
export function buildContentSecurityPolicy({
  nonce,
  supabaseUrl,
  development,
  production,
}: CspOptions): string {
  const supabaseOrigin = new URL(supabaseUrl).origin;
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
    `img-src 'self' data: blob: ${supabaseOrigin}`,
    "font-src 'self' data:",
    `connect-src 'self' ${supabaseOrigin} ${toWebSocketOrigin(supabaseOrigin)}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    ...(production ? ["upgrade-insecure-requests"] : []),
  ];

  return directives.join("; ");
}
