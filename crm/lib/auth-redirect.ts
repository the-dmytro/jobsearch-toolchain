/**
 * The origin a magic link returns to. It must be the host the sign-in form was submitted on:
 * the PKCE code verifier is a cookie on that host, and the callback on any other host cannot
 * finish the sign-in.
 *
 * The request host is trusted when:
 * - the app runs on Vercel, which routes only this project's own domains to the deployment
 *   and sets the forwarded host itself;
 * - it is a local development host;
 * - it matches the configured site URL.
 * Otherwise the configured site URL is used.
 */
export type AuthRedirectInput = {
  forwardedHost?: string | null;
  host?: string | null;
  forwardedProto?: string | null;
  siteUrl: string;
  onVercel: boolean;
};

const HOST_PATTERN = /^[a-z0-9.-]+(:\d{1,5})?$/i;

function firstValue(value?: string | null): string | undefined {
  const first = value?.split(",")[0]?.trim();
  return first ? first : undefined;
}

function isLocalHost(host: string): boolean {
  const name = host.replace(/:\d+$/, "").toLowerCase();
  return name === "localhost" || name === "127.0.0.1" || name.endsWith(".localhost");
}

function hostOf(url: string): string | undefined {
  try {
    return new URL(url).host.toLowerCase();
  } catch {
    return undefined;
  }
}

export function resolveAuthRedirectOrigin(input: AuthRedirectInput): string {
  const siteUrl = input.siteUrl.replace(/\/+$/, "");
  const host = (firstValue(input.forwardedHost) ?? firstValue(input.host))?.toLowerCase();
  if (!host || !HOST_PATTERN.test(host)) return siteUrl;

  const local = isLocalHost(host);
  const trusted = input.onVercel || local || host === hostOf(siteUrl);
  if (!trusted) return siteUrl;

  const proto = firstValue(input.forwardedProto)?.toLowerCase();
  const protocol = proto === "http" || proto === "https" ? proto : local ? "http" : "https";
  // Plain http only for local development hosts.
  return `${local ? protocol : "https"}://${host}`;
}
