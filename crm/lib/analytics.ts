import { eachWeekOfInterval, format, startOfWeek } from "date-fns";

import { fetchAll } from "@/lib/fetch-all";
import {
  applicationOutcome,
  bestOutcome,
  isOpenOutcome,
  isStageChangeEvent,
  isTerminal,
  normalizeStage,
  stageFromEvent,
  stageIndex,
  type StageKey,
  type StageOutcome,
} from "@/lib/stages";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

/* ------------------------------------------------------------------ */
/* Public types                                                        */
/* ------------------------------------------------------------------ */

export type DateBounds = {
  start: Date;
  end: Date;
};

/** A ratio with its sample size. `value` is 0..1, or null when `n` is 0. */
export type Rate = {
  value: number | null;
  n: number;
};

export type UpcomingItem = {
  at: string;
  label: string;
  href: string;
};

export type DashboardKpis = {
  /** Applications open now (offers still awaiting a decision count as open). */
  openApplications: number;
  /** Applications that were open at the end of the previous period. */
  openApplicationsPrev: number;
  appliedInRange: number;
  appliedPrevPeriod: number;
  responseRate: Rate;
  responseRatePrev: Rate;
  /** Interviews whose scheduled_at is in range and not in the future. */
  interviewsInRange: number;
  interviewsPrev: number;
  /** Applications applied in range that reached the offer stage (cohort, same rule as the funnel). */
  offersInRange: number;
  offersPrev: number;
  newOpportunities: number;
  newOpportunitiesPrev: number;
  avgScore: number | null;
  avgScorePrev: number | null;
};

export type FunnelStepKey = "applied" | "screening" | "interview" | "final" | "offer";

/**
 * One step of the cohort funnel. `count` is cumulative: applications that reached this stage
 * or a later one. Counts never increase down the funnel, so each conversion is at most 100%.
 */
export type FunnelStep = {
  key: FunnelStepKey;
  label: string;
  count: number;
  /** Conversion from the previous step: count / previous count. Null for the first step. */
  conversion: Rate | null;
};

/** Sourcing activity in the selected range, shown beside the cohort funnel. */
export type SourcingStats = {
  /** Opportunities created in range. */
  opportunitiesFound: number;
  /** Opportunities created in range that have at least one evaluation. */
  opportunitiesEvaluated: number;
  /** Applications whose applied date (or created date) is in range. */
  applied: number;
};

/** Cohort funnel: applications applied in range, counted by the furthest stage they reached. */
export type FunnelSummary = {
  steps: FunnelStep[];
  sourcing: SourcingStats;
};

export type WeeklyActivityPoint = {
  /** Monday of the ISO week, yyyy-MM-dd (local). */
  weekStart: string;
  opportunities: number;
  applied: number;
  /** Applications with a first response (reply, invite, stage change, inbound message) in this week. */
  responses: number;
  interviews: number;
};

export type SourceEffectiveness = {
  providerId: string | null;
  slug: string;
  name: string;
  opportunities: number;
  applications: number;
  applicationsWithInterview: number;
  /** Applications with any response (reply, invite, stage change past applied, inbound message). */
  applicationsWithResponse: number;
  responseRate: Rate;
  offers: number;
  appToInterview: Rate;
};

export type PipelineAgingRow = {
  applicationId: string;
  company: string;
  title: string;
  stage: StageKey;
  daysInStage: number;
  appliedAt: string | null;
};

export type AttentionInterview = {
  interviewId: string;
  applicationId: string;
  scheduledAt: string;
  stage: string | null;
  company: string;
};

export type StalledApplication = {
  applicationId: string;
  company: string;
  title: string;
  stage: StageKey;
  daysInStage: number;
};

export type RunError = {
  runId: string;
  startedAt: string;
  provider: string;
  summary: string | null;
};

export type AttentionBundle = {
  upcomingInterviews: AttentionInterview[];
  stalled: StalledApplication[];
  runErrors: RunError[];
};

export type DataTotals = {
  applications: number;
  opportunities: number;
  interviews: number;
  evaluations: number;
  communications: number;
  automationRuns: number;
};

export type DashboardBundle = {
  kpis: DashboardKpis;
  weeklyActivity: WeeklyActivityPoint[];
  funnel: FunnelSummary;
  sourceEffectiveness: SourceEffectiveness[];
  pipelineAging: PipelineAgingRow[];
  upcoming: UpcomingItem[];
  attention: AttentionBundle;
  totals: DataTotals;
  runs: Tables<"automation_runs">[];
  runEvents: Tables<"automation_run_events">[];
};

export type ScoreBucket = "0-2" | "3-4" | "5-6" | "7-8" | "9-10" | "unknown";

export type ScoreOutcomeRow = {
  bucket: ScoreBucket;
  evaluations: number;
  /** Evaluations whose opportunity has at least one application. */
  withApplication: number;
  /** Evaluations whose best application outcome is an offer. */
  offers: number;
  /** Evaluations whose best application outcome is declined. */
  declined: number;
  /** Evaluations whose best application outcome is still open. */
  open: number;
  /** offers / withApplication. `n` is withApplication. */
  offerRate: Rate;
  avgScore: number | null;
};

export type OutcomeBreakdown = {
  outcome: StageOutcome;
  label: string;
  count: number;
};

export type DeclineReason = {
  reason: string;
  count: number;
};

/** Compensation averages for one currency and seniority. Currencies are never mixed. */
export type CompensationRow = {
  currency: string;
  seniority: string;
  avgMin: number | null;
  avgMax: number | null;
  /** Opportunities in this group. */
  count: number;
};

export type InterviewOutcome = {
  stage: string;
  result: string;
  count: number;
};

export type InsightsBundle = {
  scoreOutcomes: ScoreOutcomeRow[];
  outcomeBreakdown: OutcomeBreakdown[];
  /** Top eight decline reasons in range, most frequent first. */
  declineReasons: DeclineReason[];
  /** Applications in range whose decline reason is not among `declineReasons`, summed. */
  declineOther: number;
  compensationBySeniority: CompensationRow[];
  interviewOutcomes: InterviewOutcome[];
};

/* ------------------------------------------------------------------ */
/* Row shapes read from Supabase                                       */
/* ------------------------------------------------------------------ */

export type OpportunityRow = Pick<
  Tables<"opportunities">,
  | "id"
  | "title"
  | "organization_id"
  | "provider_id"
  | "created_at"
  | "seniority"
  | "compensation_min"
  | "compensation_max"
  | "compensation_currency"
>;

export type EvaluationRow = Pick<Tables<"evaluations">, "id" | "opportunity_id" | "score" | "evaluated_at">;

export type CommunicationRow = Pick<
  Tables<"communications">,
  "id" | "application_id" | "direction" | "sent_at" | "created_at"
>;

export type OrganizationRow = Pick<Tables<"organizations">, "id" | "name">;

export type ProviderRow = Pick<Tables<"providers">, "id" | "name" | "slug">;

const OPPORTUNITY_COLUMNS =
  "id, title, organization_id, provider_id, created_at, seniority, compensation_min, compensation_max, compensation_currency";
const EVALUATION_COLUMNS = "id, opportunity_id, score, evaluated_at";
const COMMUNICATION_COLUMNS = "id, application_id, direction, sent_at, created_at";
const ORGANIZATION_COLUMNS = "id, name";
const PROVIDER_COLUMNS = "id, name, slug";

export type DashboardInput = {
  applications: Tables<"applications">[];
  events: Tables<"application_events">[];
  interviews: Tables<"interviews">[];
  opportunities: OpportunityRow[];
  evaluations: EvaluationRow[];
  communications: CommunicationRow[];
  organizations: OrganizationRow[];
  providers: ProviderRow[];
  recentRuns: Tables<"automation_runs">[];
  recentRunEvents: Tables<"automation_run_events">[];
  failedRuns: Tables<"automation_runs">[];
};

export type InsightsInput = {
  applications: Tables<"applications">[];
  interviews: Tables<"interviews">[];
  opportunities: OpportunityRow[];
  evaluations: EvaluationRow[];
};

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const DAY_MS = 24 * 60 * 60 * 1000;
const STALLED_DAYS = 14;
const ATTENTION_WINDOW_DAYS = 7;
const PIPELINE_AGING_LIMIT = 25;
const UPCOMING_LIMIT = 12;
const DECLINE_REASON_LIMIT = 8;
/** Furthest pipeline index (see stageIndex) that counts as having reached each funnel step. */
const FUNNEL_STEPS: ReadonlyArray<{ key: FunnelStepKey; label: string; minIndex: number }> = [
  { key: "applied", label: "Applied", minIndex: 0 },
  { key: "screening", label: "Screening", minIndex: 1 },
  { key: "interview", label: "Interview", minIndex: 2 },
  { key: "final", label: "Final / onsite", minIndex: 3 },
  { key: "offer", label: "Offer", minIndex: 4 },
];
const OFFER_INDEX = 4;
const FAILED_RUN_STATUSES = new Set(["failed", "error", "failure"]);
const RESPONSE_EVENT_TYPES = new Set(["reply", "interview_invite", "response"]);
const INTERVIEW_STAGES: ReadonlySet<StageKey> = new Set<StageKey>([
  "screening",
  "tech_interview",
  "onsite",
  "offer",
]);

const OUTCOME_LABELS: Readonly<Record<StageOutcome, string>> = {
  offer: "Offer",
  declined: "Declined",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
  active: "Open",
};

/* ------------------------------------------------------------------ */
/* Pure helpers                                                        */
/* ------------------------------------------------------------------ */

function toTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function inBounds(time: number | null, bounds: DateBounds): boolean {
  return time !== null && time >= bounds.start.getTime() && time <= bounds.end.getTime();
}

function previousPeriod(range: DateBounds): DateBounds {
  const durationMs = range.end.getTime() - range.start.getTime();
  return {
    start: new Date(range.start.getTime() - durationMs - 1),
    end: new Date(range.start.getTime() - 1),
  };
}

function rate(hits: number, n: number): Rate {
  return { value: n > 0 ? hits / n : null, n };
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10;
}

function groupBy<T>(rows: readonly T[], key: (row: T) => string | null | undefined): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const row of rows) {
    const k = key(row);
    if (!k) continue;
    const list = map.get(k);
    if (list) list.push(row);
    else map.set(k, [row]);
  }
  return map;
}

function scoreBucket(score: number | null): ScoreBucket {
  if (score == null || Number.isNaN(Number(score))) return "unknown";
  const value = Number(score);
  if (value < 3) return "0-2";
  if (value < 5) return "3-4";
  if (value < 7) return "5-6";
  if (value < 9) return "7-8";
  return "9-10";
}

const SCORE_BUCKET_ORDER: ScoreBucket[] = ["0-2", "3-4", "5-6", "7-8", "9-10", "unknown"];

/* ------------------------------------------------------------------ */
/* Per-application facts                                               */
/* ------------------------------------------------------------------ */

type AppFact = {
  id: string;
  opportunityId: string | null;
  providerId: string | null;
  company: string;
  title: string;
  declineReason: string | null;
  /** applied_at ?? created_at, as epoch ms. */
  appliedAt: number | null;
  stage: StageKey;
  outcome: StageOutcome;
  /** Days since the latest stage-change event, falling back to applied_at ?? created_at. */
  daysInStage: number;
  /** When the application stopped being open. Null while it is open. */
  closedAt: number | null;
  /** Earliest response evidence, or null when none. */
  responseAt: number | null;
  /**
   * Furthest pipeline index reached, from the current stage, the stage history and an offer
   * outcome. Terminal stages keep the furthest step seen before them. Never below 0.
   */
  reachedIndex: number;
  reachedInterview: boolean;
  hasInterview: boolean;
};

type BuildInput = {
  applications: Tables<"applications">[];
  events?: Tables<"application_events">[];
  interviews: Tables<"interviews">[];
  opportunities: OpportunityRow[];
  communications?: CommunicationRow[];
  organizations?: OrganizationRow[];
};

function buildAppFacts(input: BuildInput, nowMs: number): AppFact[] {
  const orgName = new Map((input.organizations ?? []).map((org) => [org.id, org.name]));
  const oppById = new Map(input.opportunities.map((opp) => [opp.id, opp]));
  const eventsByApp = groupBy(input.events ?? [], (e) => e.application_id);
  const commsByApp = groupBy(input.communications ?? [], (c) => c.application_id);
  const interviewsByApp = groupBy(input.interviews, (i) => i.application_id);

  return input.applications.map((app) => {
    const opp = app.opportunity_id ? oppById.get(app.opportunity_id) : undefined;
    const orgId = app.organization_id ?? opp?.organization_id ?? null;
    const appliedAt = toTime(app.applied_at) ?? toTime(app.created_at);
    const stage = normalizeStage(app.current_stage);
    const outcome = applicationOutcome(app);

    const changes = (eventsByApp.get(app.id) ?? [])
      .filter((e) => isStageChangeEvent(e.event_type))
      .map((e) => ({
        time: toTime(e.event_at) ?? toTime(e.created_at),
        stage: stageFromEvent(e),
      }))
      .filter((c): c is { time: number; stage: string | null } => c.time !== null)
      .sort((a, b) => a.time - b.time);

    const lastChange = changes.length > 0 ? changes[changes.length - 1].time : null;
    const daysBase = lastChange ?? appliedAt;
    const daysInStage = daysBase === null ? 0 : Math.max(0, Math.floor((nowMs - daysBase) / DAY_MS));

    let closedAt: number | null = null;
    if (!isOpenOutcome(outcome)) {
      const firstTerminal = changes.find((c) => c.stage !== null && isTerminal(c.stage));
      closedAt = firstTerminal?.time ?? toTime(app.updated_at) ?? appliedAt;
    }

    const responseTimes: number[] = [];
    for (const event of eventsByApp.get(app.id) ?? []) {
      if (!RESPONSE_EVENT_TYPES.has(event.event_type.trim().toLowerCase())) continue;
      const t = toTime(event.event_at) ?? toTime(event.created_at);
      if (t !== null) responseTimes.push(t);
    }
    for (const change of changes) {
      if (change.stage !== null && normalizeStage(change.stage) !== "applied") {
        responseTimes.push(change.time);
      }
    }
    for (const comm of commsByApp.get(app.id) ?? []) {
      if (comm.direction?.trim().toLowerCase() !== "inbound") continue;
      const t = toTime(comm.sent_at) ?? toTime(comm.created_at);
      if (t !== null) responseTimes.push(t);
    }
    let responseAt: number | null = responseTimes.length > 0 ? Math.min(...responseTimes) : null;
    if (responseAt === null && (stage !== "applied" || outcome !== "active")) {
      // Moved past applied with no dated evidence: use the last update as a fallback.
      responseAt = toTime(app.updated_at) ?? appliedAt;
    }

    const interviewTimes = (interviewsByApp.get(app.id) ?? [])
      .map((i) => toTime(i.scheduled_at))
      .filter((t): t is number => t !== null && t <= nowMs);
    const hasInterview = interviewTimes.length > 0;

    const reachedInterview =
      hasInterview ||
      INTERVIEW_STAGES.has(stage) ||
      outcome === "offer" ||
      changes.some((c) => c.stage !== null && stageIndex(c.stage) >= 1);

    let reachedIndex = Math.max(0, stageIndex(stage));
    for (const change of changes) reachedIndex = Math.max(reachedIndex, stageIndex(change.stage));
    if (outcome === "offer") reachedIndex = Math.max(reachedIndex, OFFER_INDEX);

    return {
      id: app.id,
      opportunityId: app.opportunity_id ?? null,
      providerId: app.provider_id ?? opp?.provider_id ?? null,
      company: (orgId && orgName.get(orgId)) || "Unknown company",
      title: opp?.title || "Untitled role",
      declineReason: app.decline_reason?.trim() || null,
      appliedAt,
      stage,
      outcome,
      daysInStage,
      closedAt,
      responseAt,
      reachedIndex,
      reachedInterview,
      hasInterview,
    };
  });
}

/** An application was open at time `t` if it had been applied for and had not yet closed. */
function openAt(fact: AppFact, t: number): boolean {
  return fact.appliedAt !== null && fact.appliedAt <= t && (fact.closedAt === null || fact.closedAt > t);
}

/* ------------------------------------------------------------------ */
/* Dashboard computation                                               */
/* ------------------------------------------------------------------ */

export function computeDashboardBundle(
  input: DashboardInput,
  range: DateBounds,
  now: Date = new Date()
): DashboardBundle {
  const nowMs = now.getTime();
  const prev = previousPeriod(range);
  const facts = buildAppFacts(input, nowMs);

  const allInterviewTimes = input.interviews
    .map((i) => ({ row: i, time: toTime(i.scheduled_at) }))
    .filter((x): x is { row: Tables<"interviews">; time: number } => x.time !== null);
  /** Interviews that have happened or are happening now (scheduled_at <= now). */
  const interviewTimes = allInterviewTimes.filter((x) => x.time <= nowMs);
  const interviewsIn = (bounds: DateBounds) =>
    interviewTimes.filter((x) => inBounds(x.time, bounds)).length;

  const oppTimes = input.opportunities.map((o) => ({ row: o, time: toTime(o.created_at) }));
  const oppsIn = (bounds: DateBounds) => oppTimes.filter((x) => inBounds(x.time, bounds));

  const scoredIn = (bounds: DateBounds) =>
    input.evaluations
      .filter((e) => inBounds(toTime(e.evaluated_at), bounds))
      .map((e) => e.score)
      .filter((s): s is number => s != null && !Number.isNaN(Number(s)))
      .map(Number);

  const appsIn = (bounds: DateBounds) => facts.filter((f) => inBounds(f.appliedAt, bounds));
  const responseRateFor = (list: AppFact[]) =>
    rate(list.filter((f) => f.responseAt !== null).length, list.length);

  const curApps = appsIn(range);
  const prevApps = appsIn(prev);

  const kpis: DashboardKpis = {
    openApplications: facts.filter((f) => isOpenOutcome(f.outcome)).length,
    openApplicationsPrev: facts.filter((f) => openAt(f, prev.end.getTime())).length,
    appliedInRange: curApps.length,
    appliedPrevPeriod: prevApps.length,
    responseRate: responseRateFor(curApps),
    responseRatePrev: responseRateFor(prevApps),
    interviewsInRange: interviewsIn(range),
    interviewsPrev: interviewsIn(prev),
    offersInRange: curApps.filter((f) => f.reachedIndex >= OFFER_INDEX).length,
    offersPrev: prevApps.filter((f) => f.reachedIndex >= OFFER_INDEX).length,
    newOpportunities: oppsIn(range).length,
    newOpportunitiesPrev: oppsIn(prev).length,
    avgScore: average(scoredIn(range)),
    avgScorePrev: average(scoredIn(prev)),
  };

  /*
   * Cohort funnel: applications applied in range. Each step counts the cohort members that
   * reached that stage or a later one, so counts never increase down the funnel and each
   * conversion is at most 100%. Sourcing stats are reported beside it, for the same range.
   */
  const evaluatedOppIds = new Set(input.evaluations.map((e) => e.opportunity_id));
  const counts = FUNNEL_STEPS.map((step) => ({
    key: step.key,
    label: step.label,
    count: curApps.filter((f) => f.reachedIndex >= step.minIndex).length,
  }));
  const funnel: FunnelSummary = {
    steps: counts.map((step, index) => ({
      ...step,
      conversion: index === 0 ? null : rate(step.count, counts[index - 1].count),
    })),
    sourcing: {
      opportunitiesFound: oppsIn(range).length,
      opportunitiesEvaluated: oppsIn(range).filter((o) => evaluatedOppIds.has(o.row.id)).length,
      applied: curApps.length,
    },
  };

  /* Weekly activity, Monday-anchored, clipped to the range. */
  const weeklyActivity = buildWeekly(facts, oppTimes, interviewTimes, range);

  /* Sources. */
  const sourceEffectiveness = buildSources(input, facts, interviewTimes, range);

  /* Pipeline aging and attention. */
  const openFacts = facts.filter((f) => isOpenOutcome(f.outcome) && !isTerminal(f.stage));
  const pipelineAging: PipelineAgingRow[] = [...openFacts]
    .sort((a, b) => b.daysInStage - a.daysInStage)
    .slice(0, PIPELINE_AGING_LIMIT)
    .map((f) => ({
      applicationId: f.id,
      company: f.company,
      title: f.title,
      stage: f.stage,
      daysInStage: f.daysInStage,
      appliedAt: f.appliedAt === null ? null : new Date(f.appliedAt).toISOString(),
    }));

  const providerName = new Map(input.providers.map((p) => [p.id, p.name]));
  const factById = new Map(facts.map((f) => [f.id, f]));

  const attentionWindowEnd = nowMs + ATTENTION_WINDOW_DAYS * DAY_MS;
  const upcomingInterviews: AttentionInterview[] = allInterviewTimes
    .filter((x) => x.time > nowMs && x.time <= attentionWindowEnd)
    .sort((a, b) => a.time - b.time)
    .map(({ row, time }) => ({
      interviewId: row.id,
      applicationId: row.application_id,
      scheduledAt: new Date(time).toISOString(),
      stage: row.stage,
      company: factById.get(row.application_id)?.company ?? "Unknown company",
    }));

  const stalled: StalledApplication[] = openFacts
    .filter((f) => f.daysInStage > STALLED_DAYS)
    .sort((a, b) => b.daysInStage - a.daysInStage)
    .map((f) => ({
      applicationId: f.id,
      company: f.company,
      title: f.title,
      stage: f.stage,
      daysInStage: f.daysInStage,
    }));

  const runErrors: RunError[] = input.failedRuns
    .filter((run) => FAILED_RUN_STATUSES.has(run.status.trim().toLowerCase()))
    .filter((run) => {
      const t = toTime(run.started_at) ?? toTime(run.created_at);
      return t !== null && t >= nowMs - ATTENTION_WINDOW_DAYS * DAY_MS && t <= nowMs;
    })
    .sort(
      (a, b) =>
        (toTime(b.started_at) ?? toTime(b.created_at) ?? 0) -
        (toTime(a.started_at) ?? toTime(a.created_at) ?? 0)
    )
    .map((run) => ({
      runId: run.id,
      startedAt: run.started_at ?? run.created_at,
      provider: (run.provider_id && providerName.get(run.provider_id)) || "Unknown provider",
      summary: run.summary,
    }));

  /* Upcoming: future interviews and dated application events, chronological. */
  const upcoming: UpcomingItem[] = [];
  for (const interview of input.interviews) {
    const t = toTime(interview.scheduled_at);
    if (interview.scheduled_at && t !== null && t > nowMs) {
      upcoming.push({
        at: interview.scheduled_at,
        label: `Interview${interview.stage ? ` (${interview.stage})` : ""}`,
        href: `/interviews/${interview.id}`,
      });
    }
  }
  for (const event of input.events) {
    const t = toTime(event.event_at);
    if (event.event_at && t !== null && t > nowMs) {
      upcoming.push({
        at: event.event_at,
        label: event.title ?? event.event_type,
        href: `/applications/${event.application_id}`,
      });
    }
  }
  upcoming.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  const totals: DataTotals = {
    applications: input.applications.length,
    opportunities: input.opportunities.length,
    interviews: input.interviews.length,
    evaluations: input.evaluations.length,
    communications: input.communications.length,
    automationRuns: input.recentRuns.length,
  };

  return {
    kpis,
    weeklyActivity,
    funnel,
    sourceEffectiveness,
    pipelineAging,
    upcoming: upcoming.slice(0, UPCOMING_LIMIT),
    attention: { upcomingInterviews, stalled, runErrors },
    totals,
    runs: input.recentRuns,
    runEvents: input.recentRunEvents,
  };
}

function weekKey(time: number): string {
  return format(startOfWeek(new Date(time), { weekStartsOn: 1 }), "yyyy-MM-dd");
}

function buildWeekly(
  facts: AppFact[],
  opps: Array<{ row: OpportunityRow; time: number | null }>,
  interviews: Array<{ row: Tables<"interviews">; time: number }>,
  range: DateBounds
): WeeklyActivityPoint[] {
  const candidates: number[] = [];
  for (const f of facts) if (f.appliedAt !== null) candidates.push(f.appliedAt);
  for (const o of opps) if (o.time !== null) candidates.push(o.time);
  for (const i of interviews) candidates.push(i.time);
  if (candidates.length === 0) return [];

  const start = new Date(Math.max(range.start.getTime(), Math.min(...candidates)));
  if (start.getTime() > range.end.getTime()) return [];
  const weeks = eachWeekOfInterval({ start, end: range.end }, { weekStartsOn: 1 });

  const buckets = new Map<string, Omit<WeeklyActivityPoint, "weekStart">>();
  const bucket = (key: string) => {
    let entry = buckets.get(key);
    if (!entry) {
      entry = { opportunities: 0, applied: 0, responses: 0, interviews: 0 };
      buckets.set(key, entry);
    }
    return entry;
  };

  for (const f of facts) {
    if (inBounds(f.appliedAt, range) && f.appliedAt !== null) bucket(weekKey(f.appliedAt)).applied += 1;
    if (inBounds(f.responseAt, range) && f.responseAt !== null) bucket(weekKey(f.responseAt)).responses += 1;
  }
  for (const o of opps) {
    if (inBounds(o.time, range) && o.time !== null) bucket(weekKey(o.time)).opportunities += 1;
  }
  for (const i of interviews) {
    if (inBounds(i.time, range)) bucket(weekKey(i.time)).interviews += 1;
  }

  return weeks.map((week) => {
    const key = format(week, "yyyy-MM-dd");
    const entry = buckets.get(weekKey(week.getTime()));
    return {
      weekStart: key,
      opportunities: entry?.opportunities ?? 0,
      applied: entry?.applied ?? 0,
      responses: entry?.responses ?? 0,
      interviews: entry?.interviews ?? 0,
    };
  });
}

function buildSources(
  input: DashboardInput,
  facts: AppFact[],
  interviews: Array<{ row: Tables<"interviews">; time: number }>,
  range: DateBounds
): SourceEffectiveness[] {
  const interviewedApps = new Set(interviews.map((i) => i.row.application_id));
  const providerRows = new Map(input.providers.map((p) => [p.id, p]));

  const oppsInRange = input.opportunities.filter((o) => inBounds(toTime(o.created_at), range));
  const appsInRange = facts.filter((f) => inBounds(f.appliedAt, range));

  const keys = new Set<string>(input.providers.map((p) => p.id));
  for (const o of oppsInRange) keys.add(o.provider_id ?? "");
  for (const f of appsInRange) keys.add(f.providerId ?? "");

  const rows: SourceEffectiveness[] = [];
  for (const key of keys) {
    const providerId = key === "" ? null : key;
    const provider = providerId ? providerRows.get(providerId) : undefined;
    const opps = oppsInRange.filter((o) => (o.provider_id ?? null) === providerId).length;
    const apps = appsInRange.filter((f) => (f.providerId ?? null) === providerId);
    const withInterview = apps.filter((f) => interviewedApps.has(f.id)).length;
    const withResponse = apps.filter((f) => f.responseAt !== null).length;
    const offers = apps.filter((f) => f.outcome === "offer").length;
    rows.push({
      providerId,
      slug: provider?.slug ?? (providerId ? providerId : "unassigned"),
      name: provider?.name ?? (providerId ? "Unknown provider" : "Unassigned"),
      opportunities: opps,
      applications: apps.length,
      applicationsWithInterview: withInterview,
      applicationsWithResponse: withResponse,
      responseRate: rate(withResponse, apps.length),
      offers,
      appToInterview: rate(withInterview, apps.length),
    });
  }
  return rows.sort((a, b) => b.applications - a.applications || b.opportunities - a.opportunities);
}

/* ------------------------------------------------------------------ */
/* Insights computation                                                */
/* ------------------------------------------------------------------ */

export function computeInsightsBundle(
  input: InsightsInput,
  range: DateBounds,
  now: Date = new Date()
): InsightsBundle {
  const facts = buildAppFacts(
    { applications: input.applications, interviews: input.interviews, opportunities: input.opportunities },
    now.getTime()
  );
  const curApps = facts.filter((f) => inBounds(f.appliedAt, range));

  const outcomeCounts = new Map<StageOutcome, number>();
  for (const f of curApps) outcomeCounts.set(f.outcome, (outcomeCounts.get(f.outcome) ?? 0) + 1);
  const outcomeBreakdown: OutcomeBreakdown[] = Array.from(outcomeCounts.entries())
    .map(([outcome, count]) => ({ outcome, label: OUTCOME_LABELS[outcome], count }))
    .sort((a, b) => b.count - a.count);

  const declineCounts = new Map<string, number>();
  for (const f of curApps) {
    if (f.declineReason) declineCounts.set(f.declineReason, (declineCounts.get(f.declineReason) ?? 0) + 1);
  }
  const rankedDeclines: DeclineReason[] = Array.from(declineCounts.entries())
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
  const declineReasons = rankedDeclines.slice(0, DECLINE_REASON_LIMIT);
  const declineOther = rankedDeclines
    .slice(DECLINE_REASON_LIMIT)
    .reduce((sum, row) => sum + row.count, 0);

  /* Score distribution: one row per evaluation, best outcome across its applications. */
  const appsByOpp = groupBy(facts, (f) => f.opportunityId);
  const scoreAcc = new Map<
    ScoreBucket,
    { evaluations: number; withApplication: number; offers: number; declined: number; open: number; scores: number[] }
  >();
  for (const evaluation of input.evaluations) {
    if (!inBounds(toTime(evaluation.evaluated_at), range)) continue;
    const bucket = scoreBucket(evaluation.score);
    const acc = scoreAcc.get(bucket) ?? {
      evaluations: 0,
      withApplication: 0,
      offers: 0,
      declined: 0,
      open: 0,
      scores: [],
    };
    acc.evaluations += 1;
    if (evaluation.score != null && !Number.isNaN(Number(evaluation.score))) acc.scores.push(Number(evaluation.score));
    const apps = appsByOpp.get(evaluation.opportunity_id) ?? [];
    if (apps.length > 0) {
      acc.withApplication += 1;
      const best = bestOutcome(apps.map((a) => a.outcome));
      if (best === "offer") acc.offers += 1;
      else if (best === "declined") acc.declined += 1;
      else if (best === "active") acc.open += 1;
    }
    scoreAcc.set(bucket, acc);
  }
  const scoreOutcomes: ScoreOutcomeRow[] = SCORE_BUCKET_ORDER.filter((b) => scoreAcc.has(b)).map((bucket) => {
    const acc = scoreAcc.get(bucket)!;
    return {
      bucket,
      evaluations: acc.evaluations,
      withApplication: acc.withApplication,
      offers: acc.offers,
      declined: acc.declined,
      open: acc.open,
      offerRate: rate(acc.offers, acc.withApplication),
      avgScore: average(acc.scores),
    };
  });

  /* Compensation grouped by currency and seniority. Never mixes currencies. */
  const compGroups = new Map<
    string,
    { currency: string; seniority: string; minSum: number; minCount: number; maxSum: number; maxCount: number; count: number }
  >();
  for (const opp of input.opportunities) {
    if (!inBounds(toTime(opp.created_at), range)) continue;
    const currency = opp.compensation_currency?.trim().toUpperCase() || "unknown";
    const seniority = opp.seniority?.trim().toLowerCase() || "unspecified";
    const key = `${currency}\u0000${seniority}`;
    const group = compGroups.get(key) ?? {
      currency,
      seniority,
      minSum: 0,
      minCount: 0,
      maxSum: 0,
      maxCount: 0,
      count: 0,
    };
    group.count += 1;
    if (opp.compensation_min != null) {
      group.minSum += Number(opp.compensation_min);
      group.minCount += 1;
    }
    if (opp.compensation_max != null) {
      group.maxSum += Number(opp.compensation_max);
      group.maxCount += 1;
    }
    compGroups.set(key, group);
  }
  const compensationBySeniority: CompensationRow[] = Array.from(compGroups.values())
    .map((g) => ({
      currency: g.currency,
      seniority: g.seniority,
      avgMin: g.minCount ? Math.round(g.minSum / g.minCount) : null,
      avgMax: g.maxCount ? Math.round(g.maxSum / g.maxCount) : null,
      count: g.count,
    }))
    .sort((a, b) => b.count - a.count || a.currency.localeCompare(b.currency) || a.seniority.localeCompare(b.seniority));

  /* Interview results by stage, in range by scheduled_at. */
  const interviewCounts = new Map<string, { stage: string; result: string; count: number }>();
  for (const interview of input.interviews) {
    if (!inBounds(toTime(interview.scheduled_at), range)) continue;
    const stage = interview.stage?.trim() ? normalizeStage(interview.stage) : "unknown";
    const result = interview.result?.trim().toLowerCase() || "pending";
    const key = `${stage}\u0000${result}`;
    const entry = interviewCounts.get(key) ?? { stage, result, count: 0 };
    entry.count += 1;
    interviewCounts.set(key, entry);
  }
  const interviewOutcomes = Array.from(interviewCounts.values()).sort((a, b) => b.count - a.count);

  return {
    scoreOutcomes,
    outcomeBreakdown,
    declineReasons,
    declineOther,
    compensationBySeniority,
    interviewOutcomes,
  };
}

/* ------------------------------------------------------------------ */
/* Data loading                                                        */
/* ------------------------------------------------------------------ */

type QueryError = { message: string } | null;

async function unwrapRows<T>(
  query: PromiseLike<{ data: T[] | null; error: QueryError }>
): Promise<T[]> {
  const { data, error } = await query;
  if (error) throw new Error(error.message || "Failed to load rows");
  return data ?? [];
}

export async function fetchDashboardBundle(range: DateBounds): Promise<DashboardBundle> {
  const supabase = createClient();
  const now = new Date();
  const attentionSince = new Date(now.getTime() - ATTENTION_WINDOW_DAYS * DAY_MS).toISOString();

  const [
    applications,
    events,
    interviews,
    opportunities,
    evaluations,
    communications,
    organizations,
    providers,
    recentRuns,
    recentRunEvents,
    failedRuns,
  ] = await Promise.all([
    fetchAll<Tables<"applications">>((from, to) =>
      supabase.from("applications").select("*").order("id").range(from, to)
    ),
    fetchAll<Tables<"application_events">>((from, to) =>
      supabase.from("application_events").select("*").order("id").range(from, to)
    ),
    fetchAll<Tables<"interviews">>((from, to) =>
      supabase.from("interviews").select("*").order("id").range(from, to)
    ),
    fetchAll<OpportunityRow>((from, to) =>
      supabase.from("opportunities").select(OPPORTUNITY_COLUMNS).order("id").range(from, to)
    ),
    fetchAll<EvaluationRow>((from, to) =>
      supabase.from("evaluations").select(EVALUATION_COLUMNS).order("id").range(from, to)
    ),
    fetchAll<CommunicationRow>((from, to) =>
      supabase.from("communications").select(COMMUNICATION_COLUMNS).order("id").range(from, to)
    ),
    fetchAll<OrganizationRow>((from, to) =>
      supabase.from("organizations").select(ORGANIZATION_COLUMNS).order("id").range(from, to)
    ),
    fetchAll<ProviderRow>((from, to) =>
      supabase.from("providers").select(PROVIDER_COLUMNS).order("id").range(from, to)
    ),
    unwrapRows(
      supabase.from("automation_runs").select("*").order("created_at", { ascending: false }).limit(10)
    ),
    unwrapRows(
      supabase
        .from("automation_run_events")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(50)
    ),
    fetchAll<Tables<"automation_runs">>((from, to) =>
      supabase
        .from("automation_runs")
        .select("*")
        .in("status", [...FAILED_RUN_STATUSES])
        .gte("created_at", attentionSince)
        .order("id")
        .range(from, to)
    ),
  ]);

  return computeDashboardBundle(
    {
      applications,
      events,
      interviews,
      opportunities,
      evaluations,
      communications,
      organizations,
      providers,
      recentRuns,
      recentRunEvents,
      failedRuns,
    },
    range,
    now
  );
}

export async function fetchInsightsBundle(range: DateBounds): Promise<InsightsBundle> {
  const supabase = createClient();
  const now = new Date();

  const [applications, interviews, opportunities, evaluations] = await Promise.all([
    fetchAll<Tables<"applications">>((from, to) =>
      supabase.from("applications").select("*").order("id").range(from, to)
    ),
    fetchAll<Tables<"interviews">>((from, to) =>
      supabase.from("interviews").select("*").order("id").range(from, to)
    ),
    fetchAll<OpportunityRow>((from, to) =>
      supabase.from("opportunities").select(OPPORTUNITY_COLUMNS).order("id").range(from, to)
    ),
    fetchAll<EvaluationRow>((from, to) =>
      supabase.from("evaluations").select(EVALUATION_COLUMNS).order("id").range(from, to)
    ),
  ]);

  return computeInsightsBundle({ applications, interviews, opportunities, evaluations }, range, now);
}
