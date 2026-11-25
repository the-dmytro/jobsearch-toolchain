/**
 * One stage vocabulary for the CRM. Messy values stored in `applications.current_stage`,
 * `application_events` and interviews are mapped here, and every analytic metric is
 * computed from these helpers (the SQL views use different literal lists and are not used).
 */

/** Pipeline columns in order. Kanban and the stage picker render these. */
export const CANONICAL_STAGES = [
  "applied",
  "screening",
  "tech_interview",
  "onsite",
  "offer",
  "declined",
] as const;

export type CanonicalStage = (typeof CANONICAL_STAGES)[number];

/** Stages that end an application without an accepted offer. */
export const TERMINAL_STAGES = ["declined", "withdrawn", "ghosted"] as const;
export type TerminalStage = (typeof TERMINAL_STAGES)[number];

/** Every stage a raw value can normalize to. */
export type StageKey = CanonicalStage | "withdrawn" | "ghosted";

/** Outcome category of an application. `active` means no decision yet. */
export type StageOutcome = "offer" | "declined" | "withdrawn" | "ghosted" | "active";

/** Pipeline steps used for progress. `declined` is terminal and not a step. */
const PIPELINE_STEPS: readonly CanonicalStage[] = CANONICAL_STAGES.filter(
  (stage) => stage !== "declined"
);

const TERMINAL_SET: ReadonlySet<string> = new Set<string>(TERMINAL_STAGES);

const STAGE_ALIASES: ReadonlyMap<string, StageKey> = new Map<string, StageKey>([
  // applied
  ["applied", "applied"],
  ["application", "applied"],
  ["applications", "applied"],
  ["submitted", "applied"],
  ["new", "applied"],
  ["saved", "applied"],
  ["active", "applied"],
  ["open", "applied"],
  ["in_progress", "applied"],
  // screening
  ["screening", "screening"],
  ["screen", "screening"],
  ["phone", "screening"],
  ["phone_screen", "screening"],
  ["phone_screening", "screening"],
  ["intro", "screening"],
  ["introduction", "screening"],
  ["recruiter", "screening"],
  ["recruiter_screen", "screening"],
  ["recruiter_call", "screening"],
  ["hr", "screening"],
  ["hr_screen", "screening"],
  // tech_interview
  ["tech_interview", "tech_interview"],
  ["technical", "tech_interview"],
  ["technical_interview", "tech_interview"],
  ["tech", "tech_interview"],
  ["tech_screen", "tech_interview"],
  ["tech_round", "tech_interview"],
  ["coding", "tech_interview"],
  ["coding_test", "tech_interview"],
  ["coding_challenge", "tech_interview"],
  ["system_design", "tech_interview"],
  ["system_design_interview", "tech_interview"],
  ["take_home", "tech_interview"],
  ["take_home_test", "tech_interview"],
  ["interview", "tech_interview"],
  // onsite
  ["onsite", "onsite"],
  ["on_site", "onsite"],
  ["final", "onsite"],
  ["final_round", "onsite"],
  ["final_interview", "onsite"],
  ["final_stage", "onsite"],
  ["panel", "onsite"],
  ["loop", "onsite"],
  ["virtual_onsite", "onsite"],
  // offer
  ["offer", "offer"],
  ["offer_received", "offer"],
  ["offer_extended", "offer"],
  ["offer_stage", "offer"],
  ["offer_accepted", "offer"],
  ["hired", "offer"],
  ["accepted", "offer"],
  // declined
  ["declined", "declined"],
  ["decline", "declined"],
  ["rejected", "declined"],
  ["rejection", "declined"],
  ["declined_archived", "declined"],
  ["closed", "declined"],
  // withdrawn
  ["withdrawn", "withdrawn"],
  ["withdraw", "withdrawn"],
  ["withdrew", "withdrawn"],
  ["candidate_withdrew", "withdrawn"],
  ["candidate_withdrawn", "withdrawn"],
  // ghosted
  ["ghosted", "ghosted"],
  ["ghosting", "ghosted"],
  ["no_response", "ghosted"],
  ["no_reply", "ghosted"],
]);

const STAGE_CHANGE_EVENT_TYPES: ReadonlySet<string> = new Set([
  "stage_change",
  "stage_changed",
  "stage",
]);

/** Lowercases, trims and folds spaces, hyphens and punctuation into single underscores. */
function toKey(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[\s\-/]+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
}

/** Maps a raw value to a stage key, or null when the value is not recognised. */
export function lookupStage(raw: string | null | undefined): StageKey | null {
  if (raw == null) return null;
  const key = toKey(String(raw));
  if (!key) return null;
  return STAGE_ALIASES.get(key) ?? null;
}

/** Maps a raw DB value to a stage key. Unknown and empty values fall back to `applied`. */
export function normalizeStage(raw: string | null | undefined): StageKey {
  return lookupStage(raw) ?? "applied";
}

export function isTerminal(raw: string | null | undefined): boolean {
  return TERMINAL_SET.has(normalizeStage(raw));
}

/** Position among the pipeline steps, or -1 for terminal stages. */
export function stageIndex(raw: string | null | undefined): number {
  const stage = normalizeStage(raw);
  if (TERMINAL_SET.has(stage)) return -1;
  return PIPELINE_STEPS.indexOf(stage as CanonicalStage);
}

export type StageProgress = {
  /** 0..100. Furthest pipeline step reached; a terminal stage keeps the furthest step seen in history. */
  percent: number;
  terminal: TerminalStage | null;
};

/**
 * Progress for a progress bar. `history` is the raw stage values from stage-change events
 * (oldest to newest). A declined application shows the furthest real step it reached,
 * with `terminal` set so the UI can label it instead of showing 100%.
 */
export function stageProgress(
  raw: string | null | undefined,
  history: ReadonlyArray<string | null | undefined> = []
): StageProgress {
  const stage = normalizeStage(raw);
  const terminal = TERMINAL_SET.has(stage) ? (stage as TerminalStage) : null;

  let reached = stageIndex(stage);
  if (terminal) {
    reached = 0;
    for (const entry of history) {
      reached = Math.max(reached, stageIndex(entry));
    }
  }

  const percent = Math.round(((reached + 1) / PIPELINE_STEPS.length) * 100);
  return { percent, terminal };
}

/** Outcome category for a single stage value. */
export function stageOutcome(raw: string | null | undefined): StageOutcome {
  const stage = normalizeStage(raw);
  if (stage === "offer") return "offer";
  if (stage === "declined") return "declined";
  if (stage === "withdrawn") return "withdrawn";
  if (stage === "ghosted") return "ghosted";
  return "active";
}

/**
 * Outcome implied by a free-text `outcome` or `status` value. Returns null when the value
 * is empty or unknown, and `active` for values that describe an open application.
 */
export function outcomeFromText(raw: string | null | undefined): StageOutcome | null {
  const stage = lookupStage(raw);
  if (!stage) return null;
  return stageOutcome(stage);
}

/**
 * Outcome category of an application. An explicit outcome or status that is not `active`
 * wins; otherwise the current stage decides.
 */
export function applicationOutcome(app: {
  status?: string | null;
  current_stage?: string | null;
  outcome?: string | null;
}): StageOutcome {
  const fromOutcome = outcomeFromText(app.outcome);
  if (fromOutcome && fromOutcome !== "active") return fromOutcome;
  const fromStatus = outcomeFromText(app.status);
  if (fromStatus && fromStatus !== "active") return fromStatus;
  return stageOutcome(app.current_stage);
}

/** An application still awaiting a decision (offers included, since they are not yet final). */
export function isOpenOutcome(outcome: StageOutcome): boolean {
  return outcome === "active" || outcome === "offer";
}

/** Higher is better when picking the best outcome across several applications. */
export const OUTCOME_RANK: Readonly<Record<StageOutcome, number>> = {
  offer: 4,
  active: 3,
  withdrawn: 2,
  ghosted: 1,
  declined: 0,
};

export function bestOutcome(outcomes: readonly StageOutcome[]): StageOutcome | null {
  let best: StageOutcome | null = null;
  for (const outcome of outcomes) {
    if (best === null || OUTCOME_RANK[outcome] > OUTCOME_RANK[best]) best = outcome;
  }
  return best;
}

export function isStageChangeEvent(eventType: string | null | undefined): boolean {
  if (!eventType) return false;
  return STAGE_CHANGE_EVENT_TYPES.has(toKey(eventType));
}

/**
 * Target stage of a stage-change event. Prefers `metadata.to_stage`, then the
 * `Stage → <stage>` title written by changeApplicationStage.
 */
export function stageFromEvent(event: {
  metadata?: unknown;
  title?: string | null;
}): string | null {
  const metadata = event.metadata;
  if (metadata && typeof metadata === "object" && !Array.isArray(metadata)) {
    const toStage = (metadata as Record<string, unknown>).to_stage;
    if (typeof toStage === "string" && toStage.trim()) return toStage;
  }
  const match = event.title?.match(/(?:→|->)\s*(.+)$/);
  return match?.[1]?.trim() || null;
}
