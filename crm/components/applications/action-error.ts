import { friendlyError } from "@/lib/format";
import type { ActionResult } from "@/lib/types/action-result";

/**
 * A server action that returned `{ ok: false, message }`. Its message is already
 * written for people, so it is shown as it is.
 */
export class ActionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ActionError";
  }
}

/** Returns the data of a successful action, or throws an `ActionError` with its message. */
export function unwrapAction<T>(result: ActionResult<T>): T | undefined {
  if (!result.ok) throw new ActionError(result.message);
  return result.data;
}

/**
 * Text for a mutation toast. Action messages are shown as they are. Anything
 * else (network or unexpected errors) goes through `friendlyError`, so raw
 * messages never reach the page.
 */
export function mutationMessage(error: unknown): string {
  if (error instanceof ActionError) return error.message;
  return friendlyError(error);
}
