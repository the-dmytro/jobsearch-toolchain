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
  /**
   * Allows the Vercel preview toolbar (vercel.live) to load and talk to the page. Set only for
   * preview deployments. Production and local policies do not change.
   */
  vercelPreviewToolbar?: boolean;
};

const VERCEL_LIVE = "https://vercel.live";
const VERCEL_TOOLBAR_SOCKET = "wss://ws-us3.pusher.com";
const VERCEL_TOOLBAR_IMAGE_ORIGINS = ["https://vercel.live", "https://vercel.com"];

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
  vercelPreviewToolbar = false,
}: CspOptions): string {
  const supabaseOrigins = supabaseUrl ? [new URL(supabaseUrl).origin] : [];
  const scriptSrc = [
    "'self'",
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    ...(development ? ["'unsafe-eval'"] : []),
    ...(vercelPreviewToolbar ? [VERCEL_LIVE] : []),
  ].join(" ");

  const directives = [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    [
      "img-src 'self' data: blob:",
      ...supabaseOrigins,
      ...(vercelPreviewToolbar ? VERCEL_TOOLBAR_IMAGE_ORIGINS : []),
    ].join(" "),
    "font-src 'self' data:",
    [
      "connect-src 'self'",
      ...supabaseOrigins.flatMap((o) => [o, toWebSocketOrigin(o)]),
      ...(vercelPreviewToolbar ? [VERCEL_LIVE, VERCEL_TOOLBAR_SOCKET] : []),
    ].join(" "),
    ...(vercelPreviewToolbar ? [`frame-src 'self' ${VERCEL_LIVE}`] : []),
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    ...(upgradeInsecureRequests ? ["upgrade-insecure-requests"] : []),
  ];

  return directives.join("; ");
}
