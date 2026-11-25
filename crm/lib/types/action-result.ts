/** Shape returned by every server action in lib/actions. Messages are safe to show users. */
export type ActionResult<T = void> = { ok: true; data?: T } | { ok: false; message: string };
