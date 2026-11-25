import { describe, expect, it } from "vitest";
import {
  EMPTY_VALUE,
  FALLBACK_LOCALE,
  formatCurrency,
  formatDate,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelative,
  friendlyError,
  getUserLocale,
} from "@/lib/format";

// Local-time constructors keep these tests independent of the machine time zone.
const NOW = new Date(2026, 10, 25, 12, 0, 0); // 25 Nov 2026, 12:00 local
const at = (offsetMs: number) => new Date(NOW.getTime() + offsetMs);
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

describe("formatDate", () => {
  it("formats a Date in the fallback locale as a medium date", () => {
    expect(formatDate(new Date(2026, 10, 25))).toBe("25 Nov 2026");
  });

  it("appends the time when withTime is set", () => {
    expect(formatDate(new Date(2026, 10, 25, 14, 5), { withTime: true })).toBe(
      "25 Nov 2026, 14:05"
    );
  });

  it("accepts ISO-like strings and numeric timestamps", () => {
    expect(formatDate("2026-11-25T12:00:00")).toBe("25 Nov 2026");
    expect(formatDate(new Date(2026, 10, 25, 9).getTime())).toBe("25 Nov 2026");
  });

  it("uses an explicit locale when one is given", () => {
    expect(formatDate(new Date(2026, 10, 25), { locale: "en-US" })).toBe("Nov 25, 2026");
  });

  it("falls back to en-GB for an invalid locale tag", () => {
    expect(formatDate(new Date(2026, 10, 25), { locale: "not_a_locale!!" })).toBe(
      "25 Nov 2026"
    );
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["an empty string", ""],
    ["a non-date string", "not a date"],
    ["an invalid Date", new Date("nope")],
    ["NaN", Number.NaN],
  ])("returns the em dash for %s", (_label, value) => {
    expect(formatDate(value as Date | null | undefined)).toBe(EMPTY_VALUE);
  });
});

describe("formatRelative", () => {
  it("uses future phrasing for later instants", () => {
    expect(formatRelative(at(3 * DAY), { now: NOW })).toBe("in 3 days");
  });

  it("uses past phrasing for earlier instants", () => {
    expect(formatRelative(at(-2 * HOUR), { now: NOW })).toBe("2 hours ago");
  });

  it("truncates instead of rounding partial units", () => {
    expect(formatRelative(at(-(2 * HOUR + 50 * 60 * 1000)), { now: NOW })).toBe("2 hours ago");
  });

  it("uses words for adjacent days with numeric auto", () => {
    expect(formatRelative(at(-DAY), { now: NOW })).toBe("yesterday");
    expect(formatRelative(at(DAY), { now: NOW })).toBe("tomorrow");
  });

  it("reads zero difference as now", () => {
    expect(formatRelative(at(0), { now: NOW })).toBe("now");
  });

  it("uses seconds for differences under a minute", () => {
    expect(formatRelative(at(-45 * 1000), { now: NOW })).toBe("45 seconds ago");
  });

  it("picks months and years for long gaps", () => {
    expect(formatRelative(at(-60 * DAY), { now: NOW })).toBe("2 months ago");
    expect(formatRelative(at(800 * DAY), { now: NOW })).toBe("in 2 years");
  });

  it("accepts a Date as now", () => {
    expect(formatRelative(at(HOUR), { now: new Date(NOW) })).toBe("in 1 hour");
  });

  it("returns the em dash for missing or invalid input", () => {
    expect(formatRelative(null, { now: NOW })).toBe(EMPTY_VALUE);
    expect(formatRelative("garbage", { now: NOW })).toBe(EMPTY_VALUE);
  });
});

describe("formatCurrency", () => {
  it("formats a GBP amount with grouping and two decimals", () => {
    expect(formatCurrency(1250, "GBP")).toBe("£1,250.00");
  });

  it("formats a USD amount in an explicit locale", () => {
    expect(formatCurrency(1250.5, "USD", { locale: "en-US" })).toBe("$1,250.50");
  });

  it("falls back to the number plus the code for an invalid currency code", () => {
    expect(formatCurrency(10, "US")).toBe("10 US");
  });

  it.each([null, undefined, Number.NaN, Number.POSITIVE_INFINITY])(
    "returns the em dash for %s",
    (value) => {
      expect(formatCurrency(value as number | null | undefined, "GBP")).toBe(EMPTY_VALUE);
    }
  );
});

describe("formatNumber", () => {
  it("groups thousands", () => {
    expect(formatNumber(12480)).toBe("12,480");
  });

  it("caps fraction digits at three by default", () => {
    expect(formatNumber(1.23456)).toBe("1.235");
  });

  it("respects an explicit digits cap", () => {
    expect(formatNumber(1.23456, { digits: 2 })).toBe("1.23");
    expect(formatNumber(1.5, { digits: 0 })).toBe("2");
  });

  it("treats a negative digits value as zero", () => {
    expect(formatNumber(1.6, { digits: -3 })).toBe("2");
  });

  it.each([null, undefined, Number.NaN])("returns the em dash for %s", (value) => {
    expect(formatNumber(value as number | null | undefined)).toBe(EMPTY_VALUE);
  });
});

describe("formatPercent", () => {
  it("rounds a ratio to whole percent by default", () => {
    expect(formatPercent(0.427)).toBe("43%");
  });

  it("keeps the requested number of digits", () => {
    expect(formatPercent(0.4256, 1)).toBe("42.6%");
  });

  it("does not clamp ratios above one", () => {
    expect(formatPercent(1.2)).toBe("120%");
  });

  it("shows zero as 0%", () => {
    expect(formatPercent(0)).toBe("0%");
  });

  it("treats negative digits as zero", () => {
    expect(formatPercent(0.5, -2)).toBe("50%");
  });

  it.each([null, undefined, Number.NaN])("returns the em dash for %s", (value) => {
    expect(formatPercent(value as number | null | undefined)).toBe(EMPTY_VALUE);
  });
});

describe("formatDuration", () => {
  it("uses the singular for one day", () => {
    expect(formatDuration(1)).toBe("1 day");
  });

  it("uses the plural for larger counts", () => {
    expect(formatDuration(12)).toBe("12 days");
  });

  it("keeps one decimal below ten days", () => {
    expect(formatDuration(3.46)).toBe("3.5 days");
    expect(formatDuration(0.5)).toBe("0.5 days");
  });

  it("rounds to a whole number from ten days upward", () => {
    expect(formatDuration(10.4)).toBe("10 days");
    expect(formatDuration(41.6)).toBe("42 days");
  });

  it("shows zero days", () => {
    expect(formatDuration(0)).toBe("0 days");
  });

  it.each([-1, null, undefined, Number.NaN])("returns the em dash for %s", (value) => {
    expect(formatDuration(value as number | null | undefined)).toBe(EMPTY_VALUE);
  });
});

describe("friendlyError", () => {
  it("returns the generic message for null and undefined", () => {
    expect(friendlyError(null)).toBe("Something went wrong. Please try again.");
    expect(friendlyError(undefined)).toBe("Something went wrong. Please try again.");
  });

  it("maps a Postgres insufficient-privilege code to a permission message", () => {
    const msg = friendlyError({ code: "42501", message: "some internal text" });
    expect(msg).toMatch(/permission/i);
  });

  it("maps row-level security denials to a permission message", () => {
    const msg = friendlyError({
      message: "new row violates row-level security policy for table \"applications\"",
    });
    expect(msg).toMatch(/permission/i);
  });

  it("maps a permission denied message without a code", () => {
    expect(friendlyError(new Error("permission denied for table companies"))).toMatch(
      /permission/i
    );
  });

  it("maps PostgREST anonymous-access denial to a permission message", () => {
    expect(friendlyError({ code: "PGRST302", message: "anon denied" })).toMatch(/permission/i);
  });

  it("maps an expired JWT message to a session message", () => {
    expect(friendlyError(new Error("JWT expired"))).toMatch(/session has expired/i);
  });

  it("maps the PostgREST JWT code to a session message", () => {
    expect(friendlyError({ code: "PGRST301", message: "anything" })).toMatch(/session/i);
  });

  it("maps a TypeError from fetch to a network message", () => {
    expect(friendlyError(new TypeError("Failed to fetch"))).toMatch(/reach the server/i);
  });

  it.each([
    "Failed to fetch",
    "NetworkError when attempting to fetch resource.",
    "Load failed",
    "fetch failed",
    "net::ERR_INTERNET_DISCONNECTED",
  ])("maps the message %j to a network message", (text) => {
    expect(friendlyError(new Error(text))).toMatch(/reach the server/i);
  });

  it("maps a statement timeout to a network message", () => {
    expect(
      friendlyError({ message: "canceling statement due to statement timeout" })
    ).toMatch(/reach the server/i);
  });

  it("accepts plain strings", () => {
    expect(friendlyError("fetch failed")).toMatch(/reach the server/i);
  });

  it("returns the generic message for unknown errors", () => {
    expect(friendlyError(new Error("kaboom"))).toBe("Something went wrong. Please try again.");
  });

  it("never returns raw JSON or internal details", () => {
    const inputs: unknown[] = [
      { code: "XX000", message: "boom", details: { table: "x" } },
      { code: "23505", message: "duplicate key value violates unique constraint" },
      { message: "{\"nested\":true}" },
      42,
      { weird: "object" },
    ];
    for (const input of inputs) {
      const msg = friendlyError(input);
      expect(msg).toBe("Something went wrong. Please try again.");
      expect(msg).not.toMatch(/[{}[\]]/);
    }
  });
});

describe("getUserLocale", () => {
  it("returns a non-empty BCP 47 tag", () => {
    const locale = getUserLocale();
    expect(typeof locale).toBe("string");
    expect(locale.length).toBeGreaterThan(0);
    expect(() => Intl.getCanonicalLocales(locale)).not.toThrow();
  });

  it("exposes the fallback locale constant", () => {
    expect(FALLBACK_LOCALE).toBe("en-GB");
  });
});
