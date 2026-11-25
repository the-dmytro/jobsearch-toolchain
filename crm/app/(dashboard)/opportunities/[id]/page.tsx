import { notFound } from "next/navigation";

import { OpportunityDetail } from "@/components/opportunities/opportunity-detail";
import { createClient } from "@/lib/supabase/server";

/** Postgres rejects a malformed uuid with 22P02. That is a missing record here, not a failure. */
const INVALID_UUID = "22P02";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("opportunities")
    .select("id")
    .eq("id", id)
    .maybeSingle();

  if (error && error.code !== INVALID_UUID) {
    throw new Error("This opportunity couldn't be loaded.");
  }
  if (!data || error) notFound();

  return <OpportunityDetail id={id} />;
}
