import { z } from "zod";

export const contactInsertSchema = z.object({
  organization_id: z.string().uuid().nullable().optional(),
  full_name: z.string().nullable().optional(),
  role_title: z.string().nullable().optional(),
  email: z.union([z.string().email(), z.literal("")]).optional(),
  linkedin_url: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
});
