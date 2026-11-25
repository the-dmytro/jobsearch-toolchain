/**
 * Display formatting helpers shared by the CRM screens.
 *
 * Every helper returns "—" (an em dash) for missing or invalid input instead of
 * throwing or printing "NaN", "Invalid Date" or "null", so callers can pass raw
 * database values straight through.
 *
 * Locale: helpers default to the fallback locale `en-GB`. Pass `locale` to
 * override it. `getUserLocale()` returns the browser language on the client and
 * the fallback on the server. Reading `navigator` inside a helper would make the
 * server-rendered text differ from the first client render (a hydration
 * mismatch), so opt in to the user locale from client components that render
 * after mount.
 */

export const FALLBACK_LOCALE = "en-GB";
export const EMPTY_VALUE = "—";

export type DateInput = Date | string | number | null | undefined;

/** Returns the browser language on the client, otherwise the fallback locale. */
export function getUserLocale(): string {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return FALLBACK_LOCALE;
  }
  const lang = navigator.languages?.[0] ?? navigator.language;
  return lang && isValidLocale(lang) ? lang : FALLBACK_LOCALE;
}

function isValidLocale(tag: string): boolean {
  try {
    Intl.getCanonicalLocales(tag);
    return true;
  } catch {
    return false;
  }
}

function resolveLocale(locale?: string): string {
  return locale && isValidLocale(locale) ? locale : FALLBACK_LOCALE;
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Converts a date-like value to a valid Date, or null when it is not usable. A `YYYY-MM-DD`
 * string is a calendar date (a `date` column), so it is read as local midnight, not UTC.
 */
export function parseDateValue(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "string") {
    const match = DATE_ONLY.exec(value);
    if (match) {
      const year = Number(match[1]);
      const month = Number(match[2]);
      const day = Number(match[3]);
      const local = new Date(year, month - 1, day);
      const valid =
        local.getFullYear() === year && local.getMonth() === month - 1 && local.getDate() === day;
      return valid ? local : null;
    }
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function toValidDate(value: DateInput): Date | null {
  return parseDateValue(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export type FormatDateOptions = {
  /** Append the time of day, for example "25 Nov 2026, 14:05". */
  withTime?: boolean;
  /** BCP 47 tag. Defaults to `en-GB`. */
  locale?: string;
};

/**
 * Formats a date as a short, readable string, for example "25 Nov 2026".
 *
 * @example
 * formatDate("2026-11-25")                  // "25 Nov 2026"
 * formatDate(new Date(), { withTime: true }) // "25 Nov 2026, 14:05"
 * formatDate(null)                          // "—"
 */
export function formatDate(value: DateInput, options: FormatDateOptions = {}): string {
  const date = toValidDate(value);
  if (!date) return EMPTY_VALUE;
  const formatter = new Intl.DateTimeFormat(resolveLocale(options.locale), {
    dateStyle: "medium",
    ...(options.withTime ? { timeStyle: "short" as const } : {}),
  });
  return formatter.format(date);
}

const RELATIVE_UNITS: { unit: Intl.RelativeTimeFormatUnit; seconds: number }[] = [
  { unit: "year", seconds: 365 * 24 * 60 * 60 },
  { unit: "month", seconds: 30 * 24 * 60 * 60 },
  { unit: "week", seconds: 7 * 24 * 60 * 60 },
  { unit: "day", seconds: 24 * 60 * 60 },
  { unit: "hour", seconds: 60 * 60 },
  { unit: "minute", seconds: 60 },
  { unit: "second", seconds: 1 },
];

export type FormatRelativeOptions = {
  /** Reference instant. Defaults to the current time. Pass it in tests. */
  now?: Date | number;
  /** BCP 47 tag. Defaults to `en-GB`. */
  locale?: string;
};

/**
 * Formats a date relative to now, for example "in 3 days" or "2 hours ago".
 * Uses `Intl.RelativeTimeFormat` with `numeric: "auto"`, so "yesterday" and
 * "tomorrow" come out as words where the locale has them.
 *
 * The count is truncated, not rounded, so "2h 50m ago" reads "2 hours ago".
 */
export function formatRelative(value: DateInput, options: FormatRelativeOptions = {}): string {
  const date = toValidDate(value);
  if (!date) return EMPTY_VALUE;
  const nowMs =
    options.now === undefined
      ? Date.now()
      : options.now instanceof Date
        ? options.now.getTime()
        : options.now;
  const diffSeconds = (date.getTime() - nowMs) / 1000;
  const absSeconds = Math.abs(diffSeconds);
  const sign = diffSeconds < 0 ? -1 : 1;

  const picked =
    RELATIVE_UNITS.find((u) => absSeconds >= u.seconds) ??
    RELATIVE_UNITS[RELATIVE_UNITS.length - 1];
  const amount = Math.trunc(absSeconds / picked.seconds) * sign;

  const formatter = new Intl.RelativeTimeFormat(resolveLocale(options.locale), {
    numeric: "auto",
  });
  return formatter.format(amount === 0 ? 0 : amount, picked.unit);
}

/**
 * Formats a money amount, for example "£1,250.00". An unknown or malformed
 * currency code falls back to the bare number followed by the code.
 */
export function formatCurrency(
  amount: number | null | undefined,
  currency: string,
  options: { locale?: string } = {}
): string {
  if (!isFiniteNumber(amount)) return EMPTY_VALUE;
  const locale = resolveLocale(options.locale);
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
  } catch {
    return `${new Intl.NumberFormat(locale).format(amount)} ${currency}`.trim();
  }
}

/**
 * Formats a plain number with grouping separators, for example "12,480".
 * Pass `digits` to cap the fraction digits (the default is 0 to 3).
 */
export function formatNumber(
  value: number | null | undefined,
  options: { digits?: number; locale?: string } = {}
): string {
  if (!isFiniteNumber(value)) return EMPTY_VALUE;
  return new Intl.NumberFormat(resolveLocale(options.locale), {
    maximumFractionDigits: Math.max(0, options.digits ?? 3),
  }).format(value);
}

/**
 * Formats a ratio in the range 0 to 1 as a percentage, for example
 * `formatPercent(0.427)` gives "43%". Values above 1 are shown as they are
 * (for example "120%"); they are not clamped.
 */
export function formatPercent(
  ratio: number | null | undefined,
  digits = 0,
  options: { locale?: string } = {}
): string {
  if (!isFiniteNumber(ratio)) return EMPTY_VALUE;
  // A non-finite digit count falls back to whole percentages.
  const places = Number.isFinite(digits) ? Math.min(20, Math.max(0, Math.floor(digits))) : 0;
  return new Intl.NumberFormat(resolveLocale(options.locale), {
    style: "percent",
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  }).format(ratio);
}

/**
 * Formats a count of days, for example "1 day", "12 days" or "3.5 days".
 * Values under ten keep one decimal place; larger values are rounded to a whole
 * number. Negative or non-finite input returns "—".
 */
export function formatDuration(
  days: number | null | undefined,
  options: { locale?: string } = {}
): string {
  if (!isFiniteNumber(days) || days < 0) return EMPTY_VALUE;
  const rounded = days < 10 ? Math.round(days * 10) / 10 : Math.round(days);
  return new Intl.NumberFormat(resolveLocale(options.locale), {
    style: "unit",
    unit: "day",
    unitDisplay: "long",
    maximumFractionDigits: 1,
  }).format(rounded);
}

const GENERIC_ERROR = "Something went wrong. Please try again.";
const NETWORK_ERROR = "Couldn't reach the server. Check your connection and try again.";
const PERMISSION_ERROR =
  "You don't have permission to see this. Sign out and sign back in, or ask the site owner.";
const SESSION_ERROR = "Your session has expired. Sign in again to continue.";

/** Postgres (SQLSTATE 42501, insufficient privilege) and PostgREST (anonymous access denied). */
const PERMISSION_CODES = new Set(["42501", "PGRST302"]);
/** PostgREST reports an expired or invalid JWT as PGRST301. */
const SESSION_CODES = new Set(["PGRST301"]);

const NETWORK_PATTERNS = [
  /failed to fetch/i,
  /networkerror/i,
  /network request failed/i,
  /load failed/i,
  /fetch failed/i,
  /err_internet_disconnected/i,
  /err_network/i,
];

/**
 * Turns an error of any shape into a short sentence that is safe to show a
 * person. Never returns raw JSON, stack traces or database internals.
 *
 * Mapped cases:
 * - network and fetch failures
 * - database permission or row-level security denials (SQLSTATE 42501, or "permission denied")
 * - expired sessions ("JWT expired")
 * - anything else: a generic message
 */
export function friendlyError(err: unknown): string {
  if (err === null || err === undefined) return GENERIC_ERROR;

  const { message, code } = readErrorFields(err);
  const text = message ?? "";

  if (code && SESSION_CODES.has(code)) return SESSION_ERROR;
  if (/jwt expired|token is expired|invalid jwt|session.*expired/i.test(text)) {
    return SESSION_ERROR;
  }

  if (code && PERMISSION_CODES.has(code)) return PERMISSION_ERROR;
  if (/permission denied|row-level security/i.test(text)) return PERMISSION_ERROR;

  if (err instanceof TypeError && NETWORK_PATTERNS.some((p) => p.test(text))) {
    return NETWORK_ERROR;
  }
  if (NETWORK_PATTERNS.some((p) => p.test(text)) || /timed? ?out/i.test(text)) {
    return NETWORK_ERROR;
  }

  return GENERIC_ERROR;
}

function readErrorFields(err: unknown): { message?: string; code?: string } {
  if (typeof err === "string") return { message: err };
  if (typeof err !== "object") return {};
  const record = err as Record<string, unknown>;
  const message = typeof record.message === "string" ? record.message : undefined;
  const code = typeof record.code === "string" ? record.code : undefined;
  return { message, code };
}
