import type { ZodError } from "zod";

import type { ActionResult } from "@/lib/types/action-result";

export const GENERIC_FAILURE = "Something went wrong. Try again.";

export function fail(message: string): { ok: false; message: string } {
  return { ok: false, message };
}

/** User-facing message for a failed input check. Lists field names only. */
export function invalidInput(error: ZodError): { ok: false; message: string } {
  const fields = Object.keys(error.flatten().fieldErrors);
  return fail(
    fields.length > 0
      ? `Check ${fields.join(", ")} and try again.`
      : "Check the form and try again."
  );
}

/** Server-side log of the raw error. Never returned to the client. */
export function logActionError(action: string, error: unknown): void {
  const detail =
    error && typeof error === "object" && "message" in error
      ? String((error as { message: unknown }).message)
      : String(error);
  console.error(`${action}: ${detail}`);
}

export type { ActionResult };
