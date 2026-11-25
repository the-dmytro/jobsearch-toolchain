import { z } from "zod";

import { CANONICAL_STAGES } from "@/lib/stages";

/**
 * Fields the edit sheet may write. Stage, status and outcome are deliberately absent: they move
 * only through `changeApplicationStage`, which writes them together and records the event. The
 * object is strict, so a payload that carries any of them is refused.
 */
export const applicationUpdateSchema = z.strictObject({
  id: z.string().uuid(),
  notes: z.string().nullable().optional(),
  applied_at: z.string().nullable().optional(),
  decline_reason: z.string().nullable().optional(),
  salary_requested_text: z.string().nullable().optional(),
});

export const stageChangeSchema = z.object({
  applicationId: z.string().uuid(),
  newStage: z.enum(CANONICAL_STAGES),
});

export const applicationEventSchema = z.object({
  applicationId: z.string().uuid(),
  eventType: z.string().min(1),
  title: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  eventAt: z.string().nullable().optional(),
});
