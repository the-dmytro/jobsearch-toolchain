import { timeOf } from "@/lib/activity";

/** The fields a run time is read from. */
export type RunTimeSource = {
  started_at: string | null;
  finished_at: string | null;
  run_key: string | null;
};

/** Trailing YYYYMMDDHHMMSS or YYYYMMDDHHMM stamp in a run key, as a whole token. */
const RUN_KEY_STAMP = /(?<!\d)(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?$/;
/** A calendar date written as YYYY-MM-DD anywhere in a run key. */
const RUN_KEY_DATE = /(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)/;

/**
 * Epoch ms for a UTC instant built from parts, or null when the parts are not a real date and
 * time (for example month 13 or 31 February).
 */
function utcFromParts(parts: number[]): number | null {
  const [year, month, day, hour = 0, minute = 0, second = 0] = parts;
  const time = Date.UTC(year, month - 1, day, hour, minute, second);
  const date = new Date(time);
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day ||
    date.getUTCHours() !== hour ||
    date.getUTCMinutes() !== minute ||
    date.getUTCSeconds() !== second
  ) {
    return null;
  }
  return time;
}

/** Time written into a run key, read as UTC, or null when the key carries none. */
export function runKeyTime(runKey: string | null | undefined): number | null {
  if (!runKey) return null;
  const stamp = RUN_KEY_STAMP.exec(runKey);
  if (stamp) {
    const parts = stamp.slice(1).filter((part): part is string => part !== undefined).map(Number);
    const time = utcFromParts(parts);
    if (time !== null) return time;
  }
  const date = RUN_KEY_DATE.exec(runKey);
  if (date) return utcFromParts([Number(date[1]), Number(date[2]), Number(date[3])]);
  return null;
}

/**
 * When an automation run happened, as epoch ms: started_at, else finished_at, else the time in
 * its run key. Null when none of these is known. Created and updated timestamps are never used:
 * they record when a row was written, not when the run ran.
 */
export function runTime(run: RunTimeSource): number | null {
  return timeOf(run.started_at) ?? timeOf(run.finished_at) ?? runKeyTime(run.run_key);
}

/** Orders runs newest first by runTime. Runs without a time sort last. */
export function compareRunsNewestFirst(a: RunTimeSource, b: RunTimeSource): number {
  const at = runTime(a);
  const bt = runTime(b);
  if (at === null && bt === null) return 0;
  if (at === null) return 1;
  if (bt === null) return -1;
  return bt - at;
}
