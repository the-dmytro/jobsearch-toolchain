/** Canonical funnel / kanban columns — map messy DB values here. */
export const CANONICAL_STAGES = [
  "applied",
  "screening",
  "tech_interview",
  "onsite",
  "offer",
  "declined",
] as const;

export type CanonicalStage = (typeof CANONICAL_STAGES)[number];

const aliases: Record<string, CanonicalStage> = {
  applied: "applied",
  screening: "screening",
  phone: "screening",
  intro: "screening",
  recruiter: "screening",
  technical: "tech_interview",
  tech: "tech_interview",
  coding: "tech_interview",
  system_design: "tech_interview",
  onsite: "onsite",
  final: "onsite",
  offer: "offer",
  hired: "offer",
  declined: "declined",
  rejected: "declined",
  declined_archived: "declined",
};

export function normalizeStage(raw: string | null | undefined): CanonicalStage {
  if (!raw) return "applied";
  const k = raw.trim().toLowerCase().replace(/\s+/g, "_");
  if (CANONICAL_STAGES.includes(k as CanonicalStage)) {
    return k as CanonicalStage;
  }
  return aliases[k] ?? "applied";
}

export function stageIndex(stage: string | null | undefined): number {
  const c = normalizeStage(stage);
  return CANONICAL_STAGES.indexOf(c);
}

export function stageProgressPercent(stage: string | null | undefined): number {
  const idx = stageIndex(stage);
  if (idx < 0) return 0;
  return Math.round(((idx + 1) / CANONICAL_STAGES.length) * 100);
}
