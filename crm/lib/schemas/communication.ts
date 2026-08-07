import { z } from "zod";

export const communicationInsertSchema = z.object({
  application_id: z.string().uuid().nullable().optional(),
  organization_id: z.string().uuid().nullable().optional(),
  contact_id: z.string().uuid().nullable().optional(),
  channel: z.string().nullable().optional(),
  direction: z.string().nullable().optional(),
  subject: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
  sent_at: z.string().nullable().optional(),
});
