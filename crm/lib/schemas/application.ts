import { z } from "zod";

export const applicationUpdateSchema = z.object({
  id: z.string().uuid(),
  status: z.string().optional(),
  current_stage: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  applied_at: z.string().nullable().optional(),
  decline_reason: z.string().nullable().optional(),
  outcome: z.string().nullable().optional(),
  salary_requested_text: z.string().nullable().optional(),
});

export const stageChangeSchema = z.object({
  applicationId: z.string().uuid(),
  newStage: z.string().min(1),
});

export const applicationEventSchema = z.object({
  applicationId: z.string().uuid(),
  eventType: z.string().min(1),
  title: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  eventAt: z.string().nullable().optional(),
});
