import { z } from "zod";

/**
 * Environment validation. Everything here is lazy: nothing is parsed at import
 * time, so `next build` without env vars still succeeds. Errors name the missing
 * variable and never include its value.
 */

export class EnvConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EnvConfigError";
  }
}

const emptyToUndefined = (value: unknown) =>
  typeof value === "string" && value.trim() === "" ? undefined : value;

const optionalUrl = z.preprocess(emptyToUndefined, z.url().optional());
const optionalString = z.preprocess(
  emptyToUndefined,
  z.string().trim().optional()
);

const publicEnvSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().trim().min(1),
  NEXT_PUBLIC_SITE_URL: optionalUrl,
  NEXT_PUBLIC_DEMO_MODE: optionalString,
});

const serverEnvSchema = z.object({
  SUPABASE_SERVICE_ROLE_KEY: optionalString,
  SUPABASE_SECRET_KEY: optionalString,
  SUPABASE_STORAGE_BUCKET: z.preprocess(
    emptyToUndefined,
    z.string().trim().default("job-artifacts")
  ),
  CRM_OWNER_EMAIL: optionalString,
});

export type PublicEnv = z.output<typeof publicEnvSchema>;

export type ServerEnv = {
  /** Service-role or secret key, whichever is configured (service role preferred). */
  serviceKey: string;
  storageBucket: string;
  ownerEmails: string;
};

function parseOrThrow<T extends z.ZodType>(
  schema: T,
  raw: Record<string, unknown>,
  scope: string,
  hint: string
): z.output<T> {
  const result = schema.safeParse(raw);
  if (result.success) return result.data;
  const names = [...new Set(result.error.issues.map((issue) => String(issue.path[0])))];
  throw new EnvConfigError(
    `${scope} environment is missing or invalid: ${names.join(", ")}. ${hint}`
  );
}

/**
 * Public variables, safe for browser and server. Each NEXT_PUBLIC_* value is
 * referenced literally so Next.js can inline it into the client bundle.
 */
export function getPublicEnv(): PublicEnv {
  return parseOrThrow(
    publicEnvSchema,
    {
      NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
      NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
      NEXT_PUBLIC_DEMO_MODE: process.env.NEXT_PUBLIC_DEMO_MODE,
    },
    "Public",
    "Set them in the environment and restart the server."
  );
}

/** Server-only variables. Call from server code paths only, never at module scope. */
export function getServerEnv(): ServerEnv {
  const parsed = parseOrThrow(
    serverEnvSchema,
    {
      SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY,
      SUPABASE_SECRET_KEY: process.env.SUPABASE_SECRET_KEY,
      SUPABASE_STORAGE_BUCKET: process.env.SUPABASE_STORAGE_BUCKET,
      CRM_OWNER_EMAIL: process.env.CRM_OWNER_EMAIL,
    },
    "Server",
    "Set SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) and restart the server."
  );
  const serviceKey = parsed.SUPABASE_SERVICE_ROLE_KEY ?? parsed.SUPABASE_SECRET_KEY;
  if (!serviceKey) {
    throw new EnvConfigError(
      "Server environment is missing or invalid: SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY. Set one and restart the server."
    );
  }
  return {
    serviceKey,
    storageBucket: parsed.SUPABASE_STORAGE_BUCKET,
    ownerEmails: parsed.CRM_OWNER_EMAIL ?? "",
  };
}

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

/**
 * Owner allowlist. An empty list denies everyone in production and allows
 * everyone outside production (local development without configuration).
 */
export function isAllowedOwnerEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const allow = parseOwnerEmails();
  if (allow.length === 0) {
    return process.env.NODE_ENV !== "production";
  }
  return allow.includes(email.trim().toLowerCase());
}
