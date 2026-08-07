function trimTrailingSlash(url: string): string {
  return url.replace(/\/$/, "");
}

function isLocalhostHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function isLocalhostUrl(url: string): boolean {
  try {
    return isLocalhostHost(new URL(url).hostname);
  } catch {
    return /localhost|127\.0\.0\.1/.test(url);
  }
}

function toAbsoluteUrl(urlOrHost: string): string {
  const trimmed = urlOrHost.trim();
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimTrailingSlash(trimmed);
  }
  return trimTrailingSlash(`https://${trimmed}`);
}

/** Server-side site origin for auth redirects and absolute links. */
export function resolveServerSiteUrl(): string {
  const onVercel = process.env.VERCEL === "1";
  const explicit = process.env.NEXT_PUBLIC_SITE_URL?.trim();

  if (explicit && !(onVercel && isLocalhostUrl(explicit))) {
    return trimTrailingSlash(explicit);
  }

  const productionHost = process.env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
  if (productionHost) {
    return toAbsoluteUrl(productionHost);
  }

  const deploymentHost = process.env.VERCEL_URL?.trim();
  if (deploymentHost) {
    return toAbsoluteUrl(deploymentHost);
  }

  if (explicit) {
    return trimTrailingSlash(explicit);
  }

  return "http://localhost:3000";
}

export function getSiteUrl(): string {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return resolveServerSiteUrl();
}

export function parseOwnerEmails(): string[] {
  const raw = process.env.CRM_OWNER_EMAIL ?? "";
  return raw
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

export function isAllowedOwnerEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const allow = parseOwnerEmails();
  if (allow.length === 0) {
    return process.env.NODE_ENV !== "production";
  }
  return allow.includes(email.trim().toLowerCase());
}
