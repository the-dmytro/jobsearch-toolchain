/**
 * Last activity and the stalled rule. The dashboard, the applications list and the kanban all
 * call these helpers, so an application shows the same number and the same stalled flag on every
 * screen.
 *
 * Activity is the latest moment, not in the future, that anything happened to an application: an
 * application event, a communication, a held interview, the applied date or the creation time.
 */
import { parseDateValue } from "@/lib/format";

export const DAY_MS = 24 * 60 * 60 * 1000;

/** An open application with no activity for longer than this is stalled. */
export const STALLED_DAYS = 14;

export type ActivityEventRow = { application_id: string; event_at: string | null; created_at: string };
export type ActivityCommunicationRow = { application_id: string | null; sent_at: string | null; created_at: string };
export type ActivityInterviewRow = { application_id: string; scheduled_at: string | null };

/** Timestamp in epoch ms, or null. Date-only values are read as local dates. */
export function timeOf(value: string | null | undefined): number | null {
  const date = parseDateValue(value ?? null);
  return date ? date.getTime() : null;
}

/** Latest activity per application that is not in the future, as epoch ms. */
export function latestActivityByApplication(
  sources: {
    events?: readonly ActivityEventRow[];
    communications?: readonly ActivityCommunicationRow[];
    interviews?: readonly ActivityInterviewRow[];
  },
  nowMs: number
): Map<string, number> {
  const latest = new Map<string, number>();
  const note = (applicationId: string | null | undefined, time: number | null) => {
    if (!applicationId || time === null || time > nowMs) return;
    const previous = latest.get(applicationId);
    if (previous === undefined || time > previous) latest.set(applicationId, time);
  };

  for (const event of sources.events ?? []) {
    note(event.application_id, timeOf(event.event_at) ?? timeOf(event.created_at));
  }
  for (const comm of sources.communications ?? []) {
    note(comm.application_id, timeOf(comm.sent_at) ?? timeOf(comm.created_at));
  }
  for (const interview of sources.interviews ?? []) {
    note(interview.application_id, timeOf(interview.scheduled_at));
  }
  return latest;
}

/** Last activity of one application (epoch ms), or null when nothing dated is known. */
export function lastActivityMs(
  app: { id: string; applied_at: string | null; created_at: string },
  latest: ReadonlyMap<string, number>,
  nowMs: number
): number | null {
  const candidates = [latest.get(app.id), timeOf(app.applied_at), timeOf(app.created_at)];
  let best: number | null = null;
  for (const time of candidates) {
    if (time === undefined || time === null || time > nowMs) continue;
    if (best === null || time > best) best = time;
  }
  return best;
}

/** Whole days since the given instant, never negative. Null when there is no instant. */
export function daysSince(timeMs: number | null, nowMs: number): number | null {
  if (timeMs === null) return null;
  return Math.max(0, Math.floor((nowMs - timeMs) / DAY_MS));
}

/** Stalled: still open and no activity for more than `STALLED_DAYS`. */
export function isStalled(open: boolean, days: number | null): boolean {
  return open && days !== null && days > STALLED_DAYS;
}
