import { z } from "zod";

export const interviewInsertSchema = z.object({
  application_id: z.string().uuid(),
  organization_id: z.string().uuid().nullable().optional(),
  stage: z.string().nullable().optional(),
  scheduled_at: z.string().nullable().optional(),
  meeting_url: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});
