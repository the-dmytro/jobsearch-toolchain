/**
 * One stage vocabulary for the CRM. Free-text values stored in `applications.current_stage`,
 * `applications.status`, `applications.outcome`, `application_events.event_type` and
 * `interviews.stage` are classified here, and every analytic and list rule reads from these
 * helpers. The SQL views use different literal lists and are not used.
 *
 * Text is classified with keyword rules on the lowercased value. Rules are checked in order and
 * the first match wins, most specific first. A value that matches no rule is "unrecognised" and
 * is recorded for diagnostics; the vocabulary test keeps every value the database holds
 * recognised.
 */

/** Pipeline steps in order. Progress and the cohort funnel count these. */
export const PIPELINE_STAGES = ["applied", "screening", "tech_interview", "onsite", "offer"] as const;
export type PipelineStage = (typeof PIPELINE_STAGES)[number];

/** Columns of the stage board, in order. `rejected` is shown as "Closed". */
export const CANONICAL_STAGES = [...PIPELINE_STAGES, "rejected"] as const;
export type CanonicalStage = (typeof CANONICAL_STAGES)[number];

/** Ways an application closes without an accepted offer. */
export const TERMINAL_STAGES = ["rejected", "withdrawn", "ghosted"] as const;
export type TerminalStage = (typeof TERMINAL_STAGES)[number];

/** Every stage key a raw value can normalise to. */
export type StageKey = PipelineStage | TerminalStage;

/** Outcome of an application. `active` awaits a decision, `offer` is an open offer. */
export type StageOutcome = "active" | "offer" | TerminalStage;

const TERMINAL_SET: ReadonlySet<string> = new Set<string>(TERMINAL_STAGES);

/** Outcomes that still count as open: no decision yet, or an offer awaiting a decision. */
export function isOpenOutcome(outcome: StageOutcome): boolean {
  return outcome === "active" || outcome === "offer";
}

/* ------------------------------------------------------------------ */
/* Text classification                                                 */
/* ------------------------------------------------------------------ */

/** Lowercases, turns separators into spaces and collapses runs of spaces. */
function normalizeText(raw: string | null | undefined): string {
  if (raw == null) return "";
  return String(raw)
    .toLowerCase()
    .replace(/[_\-/→]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Closing rules. Candidate-side closes are checked first, so "offer declined" is a withdrawal
 * and not a rejection.
 */
const CLOSING_RULES: ReadonlyArray<{ pattern: RegExp; value: TerminalStage }> = [
  { pattern: /\bwithdr(aw|awn|ew)\b|\boffer declined\b|\bnot taken\b/, value: "withdrawn" },
  { pattern: /\bghost(ed|ing)?\b|\bno response\b|\bno reply\b/, value: "ghosted" },
  {
    pattern:
      /\bdeclin(e|ed|es)\b|\breject(ed|ion)?\b|\brole (closed|filled)\b|\bfilled\b|\bclosed\b|\bcancell?ed by employer\b/,
    value: "rejected",
  },
];

/**
 * Stage rules, most specific first. The last rule is the applied stage, so a text that only
 * describes the application (submitted, follow-up, waiting) lands there.
 */
const STAGE_RULES: ReadonlyArray<{ pattern: RegExp; value: PipelineStage }> = [
  { pattern: /\boffer\b|\bhired\b/, value: "offer" },
  { pattern: /\bfinal\b|\bonsite\b|\bon site\b|\bloop\b|\bpanel\b/, value: "onsite" },
  {
    pattern:
      /\btechnical\b|\btech\b|\bcoding\b|\bassessment\b|\bchallenge\b|\bexercise\b|\btake home\b|\bpair programming\b|\bsystem design\b/,
    value: "tech_interview",
  },
  {
    pattern:
      /\bphone\b|\bscreen(ing)?\b|\bintro\b|\bintroduction\b|\brecruiter\b|\bhr\b|\bfirst call\b|\bfirst stage\b|\bfirst round\b|\brole discussion\b|\bget to know\b/,
    value: "screening",
  },
  { pattern: /\binterview(s|ing)?\b/, value: "tech_interview" },
  {
    pattern:
      /\bapplied\b|\bapplication\b|\bapplications\b|\bsubmitted\b|\bre ?applied\b|\breapplication\b|\bfollow up\b|\bupdate\b|\bwaiting\b|\bon hold\b|\breview\b|\bsent\b|\bnew\b|\bsaved\b|\bopen\b|\bin progress\b|\bactive\b/,
    value: "applied",
  },
];

/** Values no rule matched, with how often they were seen. Read by the vocabulary test. */
const unknownValues = new Map<string, number>();

/** What one free-text value says about a stage. */
export type StageReading = {
  /** Furthest pipeline stage the text describes. Null when it says nothing about progress. */
  stage: PipelineStage | null;
  /** Closing outcome the text describes, or null when it does not close the application. */
  closed: TerminalStage | null;
  /** False when no rule matched a non-empty value. Such values are counted as unknown. */
  recognised: boolean;
};

function firstMatch<T>(rules: ReadonlyArray<{ pattern: RegExp; value: T }>, text: string): T | null {
  for (const rule of rules) {
    if (rule.pattern.test(text)) return rule.value;
  }
  return null;
}

/** Classifies one free-text stage, status, outcome or interview stage. */
export function readStage(raw: string | null | undefined): StageReading {
  const text = normalizeText(raw);
  if (!text) return { stage: null, closed: null, recognised: true };

  const closed = firstMatch(CLOSING_RULES, text);
  const stage = firstMatch(STAGE_RULES, text);
  const recognised = closed !== null || stage !== null;
  if (!recognised) recordUnknown(String(raw));
  return { stage, closed, recognised };
}

function recordUnknown(raw: string) {
  if (process.env.NODE_ENV === "production") return;
  unknownValues.set(raw, (unknownValues.get(raw) ?? 0) + 1);
}

/** Raw values that no rule recognised since the last reset. Development and tests only. */
export function unknownStageValues(): string[] {
  return Array.from(unknownValues.keys());
}

export function resetUnknownStageValues(): void {
  unknownValues.clear();
}

/** Index of a pipeline stage, or -1 for none. */
function pipelineIndex(stage: PipelineStage | null): number {
  return stage === null ? -1 : PIPELINE_STAGES.indexOf(stage);
}

function furthest(stages: ReadonlyArray<PipelineStage | null>): PipelineStage | null {
  let best: PipelineStage | null = null;
  for (const stage of stages) {
    if (stage !== null && pipelineIndex(stage) > pipelineIndex(best)) best = stage;
  }
  return best;
}

/* ------------------------------------------------------------------ */
/* Single values                                                       */
/* ------------------------------------------------------------------ */

/**
 * Maps one raw value to a stage key: the closing outcome when the text closes the application,
 * otherwise its pipeline stage. Empty and unrecognised values fall back to `applied`.
 */
export function normalizeStage(raw: string | null | undefined): StageKey {
  const reading = readStage(raw);
  if (reading.closed) return reading.closed;
  return reading.stage ?? "applied";
}

/** Like `normalizeStage`, but null when the value is empty or not recognised. */
export function lookupStage(raw: string | null | undefined): StageKey | null {
  if (!normalizeText(raw)) return null;
  return readStage(raw).recognised ? normalizeStage(raw) : null;
}

export function isTerminal(raw: string | null | undefined): boolean {
  return TERMINAL_SET.has(normalizeStage(raw));
}

/** Position among the pipeline stages, or -1 for a closed value. */
export function stageIndex(raw: string | null | undefined): number {
  const key = normalizeStage(raw);
  if (TERMINAL_SET.has(key)) return -1;
  return PIPELINE_STAGES.indexOf(key as PipelineStage);
}

/** Outcome category for a single stage value. */
export function stageOutcome(raw: string | null | undefined): StageOutcome {
  const key = normalizeStage(raw);
  if (TERMINAL_SET.has(key)) return key as TerminalStage;
  return key === "offer" ? "offer" : "active";
}

/**
 * Outcome implied by a free-text `outcome` or `status` value. Null when the value is empty or
 * not recognised, `active` or `offer` for open values, and a closing outcome otherwise.
 */
export function outcomeFromText(raw: string | null | undefined): StageOutcome | null {
  if (!normalizeText(raw)) return null;
  const reading = readStage(raw);
  if (!reading.recognised) return null;
  if (reading.closed) return reading.closed;
  return reading.stage === "offer" ? "offer" : "active";
}

/* ------------------------------------------------------------------ */
/* Whole applications                                                  */
/* ------------------------------------------------------------------ */

export type ApplicationStageState = {
  /** Furthest pipeline stage reached, including the step before a close. Never below applied. */
  stage: PipelineStage;
  outcome: StageOutcome;
  /** True until the application closes. An open offer counts as open. */
  open: boolean;
};

/**
 * Effective state of an application from its stage, status and outcome. A closing signal in any
 * of them closes it, and the outcome field is checked first. Status "interviewing" lifts an
 * application to at least screening.
 */
export function classifyApplication(app: {
  current_stage?: string | null;
  status?: string | null;
  outcome?: string | null;
}): ApplicationStageState {
  const stageRead = readStage(app.current_stage);
  const statusRead = readStage(app.status);
  const outcomeRead = readStage(app.outcome);

  const statusStage: PipelineStage | null =
    normalizeText(app.status) === "interviewing" ? "screening" : statusRead.stage;
  const stage = furthest([stageRead.stage, statusStage, outcomeRead.stage]) ?? "applied";

  const closed = outcomeRead.closed ?? statusRead.closed ?? stageRead.closed;
  if (closed) return { stage, outcome: closed, open: false };
  return { stage, outcome: stage === "offer" ? "offer" : "active", open: true };
}

/** Outcome category of an application. See `classifyApplication`. */
export function applicationOutcome(app: {
  status?: string | null;
  current_stage?: string | null;
  outcome?: string | null;
}): StageOutcome {
  return classifyApplication(app).outcome;
}

/** Higher is better when picking the best outcome across several applications. */
export const OUTCOME_RANK: Readonly<Record<StageOutcome, number>> = {
  offer: 4,
  active: 3,
  withdrawn: 2,
  ghosted: 1,
  rejected: 0,
};

export function bestOutcome(outcomes: readonly StageOutcome[]): StageOutcome | null {
  let best: StageOutcome | null = null;
  for (const outcome of outcomes) {
    if (best === null || OUTCOME_RANK[outcome] > OUTCOME_RANK[best]) best = outcome;
  }
  return best;
}

/**
 * Status and outcome written with a stage. A pipeline stage clears any closing outcome; Closed
 * records an employer rejection.
 */
export function statusAndOutcomeForStage(stage: CanonicalStage): {
  status: string;
  outcome: string | null;
} {
  switch (stage) {
    case "applied":
      return { status: "applied", outcome: null };
    case "offer":
      return { status: "offer", outcome: null };
    case "rejected":
      return { status: "rejected", outcome: "rejected" };
    default:
      return { status: "interviewing", outcome: null };
  }
}

/* ------------------------------------------------------------------ */
/* Progress                                                            */
/* ------------------------------------------------------------------ */

export type StageProgress = {
  /** 0..100. Furthest pipeline step reached; a closed application keeps the furthest step it reached. */
  percent: number;
  terminal: TerminalStage | null;
};

/**
 * Progress for a progress bar. `history` holds the raw stage values from stage events (oldest to
 * newest). A closed application shows the furthest real step it reached, with `terminal` set so
 * the UI can label it instead of showing 100%.
 */
export function stageProgress(
  raw: string | null | undefined,
  history: ReadonlyArray<string | null | undefined> = []
): StageProgress {
  const key = normalizeStage(raw);
  const terminal = TERMINAL_SET.has(key) ? (key as TerminalStage) : null;

  let reached = Math.max(0, stageIndex(raw));
  if (terminal) {
    reached = Math.max(0, pipelineIndex(readStage(raw).stage));
    for (const entry of history) reached = Math.max(reached, stageIndex(entry));
  }

  const percent = Math.round(((reached + 1) / PIPELINE_STAGES.length) * 100);
  return { percent, terminal };
}

/* ------------------------------------------------------------------ */
/* Events and interviews                                               */
/* ------------------------------------------------------------------ */

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

/** What an application event says about the application. */
export type EventEvidence = {
  /** Listed in the vocabulary. Unlisted types still count as activity. */
  known: boolean;
  /** Pipeline stage the event shows the application reached. */
  stage: PipelineStage | null;
  /** An employer or recruiter answered the application. */
  response: boolean;
  /** The event closes the application. */
  closing: boolean;
};

const NO_EVIDENCE: Omit<EventEvidence, "known"> = {
  stage: null,
  response: false,
  closing: false,
};

const EVENT_EVIDENCE: Readonly<Record<string, Omit<EventEvidence, "known">>> = {
  // Own actions and automatic acknowledgements: no response.
  applied: { ...NO_EVIDENCE, stage: "applied" },
  application_received: NO_EVIDENCE,
  application_update: NO_EVIDENCE,
  follow_up: NO_EVIDENCE,
  candidate_reply: NO_EVIDENCE,
  opportunity_shared: NO_EVIDENCE,
  client_submission: { ...NO_EVIDENCE, stage: "applied" },
  future_consideration: NO_EVIDENCE,
  gdpr: NO_EVIDENCE,
  interview_cancelled: NO_EVIDENCE,
  // Interviews and invitations.
  interview_scheduled: { ...NO_EVIDENCE, stage: "tech_interview", response: true },
  interview_completed: { ...NO_EVIDENCE, stage: "tech_interview" },
  assessment_invited: { ...NO_EVIDENCE, stage: "tech_interview", response: true },
  recruiter_contact: { ...NO_EVIDENCE, stage: "screening", response: true },
  info_request: { ...NO_EVIDENCE, stage: "screening", response: true },
  offer: { ...NO_EVIDENCE, stage: "offer", response: true },
  offer_meeting: { ...NO_EVIDENCE, stage: "offer", response: true },
  // Closing messages from the employer.
  rejected: { ...NO_EVIDENCE, response: true, closing: true },
  rejection_received: { ...NO_EVIDENCE, response: true, closing: true },
  declined: { ...NO_EVIDENCE, response: true, closing: true },
  role_closed: { ...NO_EVIDENCE, response: true, closing: true },
};

/** Evidence for one event type. Stage changes are read from their target value, not here. */
export function eventEvidence(eventType: string | null | undefined): EventEvidence {
  const key = toKey(String(eventType ?? ""));
  const entry = EVENT_EVIDENCE[key];
  if (entry) return { known: true, ...entry };
  return { known: isStageChangeEvent(eventType), ...NO_EVIDENCE };
}

/**
 * Stage an interview row shows the application reached. An interview row always means an
 * interview happened, so an unrecognised or empty stage counts as the interview step.
 */
export function interviewStage(raw: string | null | undefined): PipelineStage {
  return readStage(raw).stage ?? "tech_interview";
}

/** Interview results that mean the interview did not take place. */
const NOT_HELD_RESULTS: ReadonlySet<string> = new Set(["cancelled", "rescheduled"]);

/** An interview counts as held once its time has passed and it was not cancelled or moved. */
export function isInterviewHeld(result: string | null | undefined, time: number | null, nowMs: number): boolean {
  if (time === null || time > nowMs) return false;
  return !NOT_HELD_RESULTS.has((result ?? "").trim().toLowerCase());
}
