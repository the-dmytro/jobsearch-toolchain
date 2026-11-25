import {
  differenceInCalendarDays,
  eachWeekOfInterval,
  endOfDay,
  format,
  startOfDay,
  startOfWeek,
  subDays,
} from "date-fns";

import type { DateRangeValue } from "@/lib/date-range-context";
import {
  daysSince,
  isStalled,
  lastActivityMs,
  latestActivityByApplication,
  timeOf,
  DAY_MS,
  type ActivityCommunicationRow,
  type ActivityEventRow,
} from "@/lib/activity";
import { fetchAll, queryError, type KeysetRow, type PageError } from "@/lib/fetch-all";
import {
  PIPELINE_STAGES,
  bestOutcome,
  classifyApplication,
  eventEvidence,
  interviewStage,
  isInterviewHeld,
  isStageChangeEvent,
  readStage,
  stageFromEvent,
  type PipelineStage,
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
  /** Applications with any response evidence, out of those applied in range. */
  responseRate: Rate;
  responseRatePrev: Rate;
  /** Interviews held in range: scheduled in range, not in the future, not cancelled or rescheduled. */
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
  /** Applications with a first response in this week. */
  responses: number;
  /** Interviews held in this week. */
  interviews: number;
};

export type SourceEffectiveness = {
  providerId: string | null;
  slug: string;
  name: string;
  opportunities: number;
  applications: number;
  applicationsWithInterview: number;
  /** Applications with any response evidence. */
  applicationsWithResponse: number;
  responseRate: Rate;
  offers: number;
  appToInterview: Rate;
};

export type PipelineAgingRow = {
  applicationId: string;
  company: string;
  title: string;
  stage: PipelineStage;
  /** Whole days since the last activity on the application. */
  daysSinceActivity: number;
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
  stage: PipelineStage;
  daysSinceActivity: number;
};

export type RunError = {
  runId: string;
  startedAt: string;
  provider: string;
  summary: string | null;
  /** `failed` is an error; `partial` is a warning that some work was not completed. */
  severity: "failed" | "partial";
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
  /** Evaluations whose best application outcome is a rejection. */
  rejected: number;
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

export type ApplicationRow = Pick<
  Tables<"applications">,
  | "id"
  | "opportunity_id"
  | "organization_id"
  | "provider_id"
  | "status"
  | "current_stage"
  | "applied_at"
  | "outcome"
  | "decline_reason"
  | "created_at"
  | "updated_at"
>;

export type EventRow = Pick<
  Tables<"application_events">,
  "id" | "application_id" | "event_type" | "event_at" | "created_at" | "title" | "metadata"
>;

export type InterviewRow = Pick<
  Tables<"interviews">,
  "id" | "application_id" | "stage" | "scheduled_at" | "result"
>;

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

const APPLICATION_COLUMNS =
  "id, opportunity_id, organization_id, provider_id, status, current_stage, applied_at, outcome, decline_reason, created_at, updated_at";
const EVENT_COLUMNS = "id, application_id, event_type, event_at, created_at, title, metadata";
const INTERVIEW_COLUMNS = "id, application_id, stage, scheduled_at, result";
const OPPORTUNITY_COLUMNS =
  "id, title, organization_id, provider_id, created_at, seniority, compensation_min, compensation_max, compensation_currency";
const EVALUATION_COLUMNS = "id, opportunity_id, score, evaluated_at";
const COMMUNICATION_COLUMNS = "id, application_id, direction, sent_at, created_at";
const ORGANIZATION_COLUMNS = "id, name";
const PROVIDER_COLUMNS = "id, name, slug";

/**
 * Everything the dashboard and insights need, read once and shared by every date range. Each
 * table is read with narrow columns; the bundles are computed from this in memory.
 */
export type RawAnalytics = {
  applications: ApplicationRow[];
  events: EventRow[];
  interviews: InterviewRow[];
  opportunities: OpportunityRow[];
  evaluations: EvaluationRow[];
  communications: CommunicationRow[];
  organizations: OrganizationRow[];
  providers: ProviderRow[];
  /** Latest automation runs, for the run health card. */
  recentRuns: Tables<"automation_runs">[];
  recentRunEvents: Tables<"automation_run_events">[];
  /** Failed and partial runs from the last seven days. */
  failedRuns: Tables<"automation_runs">[];
  /** Every automation run, counted by the server. */
  runCount: number;
};

export type DashboardInput = RawAnalytics;

export type InsightsInput = Pick<
  RawAnalytics,
  "applications" | "interviews" | "opportunities" | "evaluations"
>;

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const ATTENTION_WINDOW_DAYS = 7;
const PIPELINE_AGING_LIMIT = 25;
const UPCOMING_LIMIT = 12;
const DECLINE_REASON_LIMIT = 8;
/** Furthest pipeline stage that counts as having reached each funnel step. */
const FUNNEL_STEPS: ReadonlyArray<{ key: FunnelStepKey; label: string; minIndex: number }> = [
  { key: "applied", label: "Applied", minIndex: 0 },
  { key: "screening", label: "Screening", minIndex: 1 },
  { key: "interview", label: "Interview", minIndex: 2 },
  { key: "final", label: "Final / onsite", minIndex: 3 },
  { key: "offer", label: "Offer", minIndex: 4 },
];
const OFFER_INDEX = 4;
const FAILED_RUN_STATUS = "failed";
const PARTIAL_RUN_STATUS = "partial";

export const OUTCOME_LABELS: Readonly<Record<StageOutcome, string>> = {
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
  active: "Open",
};

/* ------------------------------------------------------------------ */
/* Pure helpers                                                        */
/* ------------------------------------------------------------------ */

function inBounds(time: number | null, bounds: DateBounds): boolean {
  return time !== null && time >= bounds.start.getTime() && time <= bounds.end.getTime();
}

/**
 * The period of the same length that ends the day before `range` starts. Calendar-day
 * arithmetic, so daylight saving changes do not shift the window.
 */
export function previousPeriod(range: DateBounds): DateBounds {
  const days = differenceInCalendarDays(range.end, range.start) + 1;
  return {
    start: startOfDay(subDays(range.start, days)),
    end: endOfDay(subDays(range.start, 1)),
  };
}

/**
 * The range a bundle is computed for. "All time" starts at the earliest dated record, so the
 * charts do not run back to 2020. Other presets are used as they are.
 */
export function resolveRange(
  value: DateRangeValue,
  input: { applications: readonly ApplicationRow[]; opportunities: readonly OpportunityRow[] }
): DateBounds {
  if (value.preset !== "all") return value.range;
  let earliest: number | null = null;
  const dates = [
    ...input.applications.map((app) => app.applied_at ?? app.created_at),
    ...input.opportunities.map((opp) => opp.created_at),
  ];
  for (const date of dates) {
    const time = timeOf(date);
    if (time !== null && (earliest === null || time < earliest)) earliest = time;
  }
  return {
    start: earliest === null ? value.range.start : startOfDay(new Date(earliest)),
    end: value.range.end,
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

function pipelineRank(stage: PipelineStage | null): number {
  return stage === null ? -1 : PIPELINE_STAGES.indexOf(stage);
}

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
  /** applied_at, or created_at when there is no applied date, as epoch ms. */
  appliedAt: number | null;
  /** Furthest pipeline stage reached, from the current values and the event and interview history. */
  stage: PipelineStage;
  outcome: StageOutcome;
  open: boolean;
  /** Whole days since the last activity, in the past. */
  daysSinceActivity: number;
  /**
   * When the application closed, from its first closing event. For an application closed with no
   * dated signal this is the applied date, so it is not open in any earlier period. Null while open.
   */
  closedAt: number | null;
  /** Any response evidence: a reply, an invitation, an inbound message, an interview or a rejection. */
  responded: boolean;
  /** Earliest dated response evidence, or null. */
  responseAt: number | null;
  /** Index of the furthest pipeline stage reached (see PIPELINE_STAGES). Never below 0. */
  reachedIndex: number;
};

type FactInput = {
  applications: ApplicationRow[];
  events?: EventRow[];
  interviews: InterviewRow[];
  opportunities: OpportunityRow[];
  communications?: CommunicationRow[];
  organizations?: OrganizationRow[];
};

function buildAppFacts(input: FactInput, nowMs: number): AppFact[] {
  const orgName = new Map((input.organizations ?? []).map((org) => [org.id, org.name]));
  const oppById = new Map(input.opportunities.map((opp) => [opp.id, opp]));
  const events = input.events ?? [];
  const communications = input.communications ?? [];
  const eventsByApp = groupBy(events, (e) => e.application_id);
  const commsByApp = groupBy(communications, (c) => c.application_id);
  const interviewsByApp = groupBy(input.interviews, (i) => i.application_id);
  const latest = latestActivityByApplication(
    {
      events: events as ActivityEventRow[],
      communications: communications as ActivityCommunicationRow[],
      interviews: input.interviews,
    },
    nowMs
  );

  return input.applications.map((app) => {
    const opp = app.opportunity_id ? oppById.get(app.opportunity_id) : undefined;
    const orgId = app.organization_id ?? opp?.organization_id ?? null;
    const appliedAt = timeOf(app.applied_at) ?? timeOf(app.created_at);
    const state = classifyApplication(app);
    const interviews = interviewsByApp.get(app.id) ?? [];

    let reachedIndex = pipelineRank(state.stage);
    const closingTimes: number[] = [];
    const responseTimes: number[] = [];
    let responded = false;

    for (const event of eventsByApp.get(app.id) ?? []) {
      const time = timeOf(event.event_at) ?? timeOf(event.created_at);
      if (isStageChangeEvent(event.event_type)) {
        // Stage changes written by the CRM: the target stage counts as reached, a closed target
        // closes the application, and they are not employer responses.
        const target = readStage(stageFromEvent(event));
        reachedIndex = Math.max(reachedIndex, pipelineRank(target.stage));
        if (target.closed && time !== null) closingTimes.push(time);
        continue;
      }
      const evidence = eventEvidence(event.event_type);
      reachedIndex = Math.max(reachedIndex, pipelineRank(evidence.stage));
      if (evidence.closing && time !== null) closingTimes.push(time);
      if (evidence.response) {
        responded = true;
        if (time !== null) responseTimes.push(time);
      }
    }

    for (const comm of commsByApp.get(app.id) ?? []) {
      if (comm.direction?.trim().toLowerCase() !== "inbound") continue;
      responded = true;
      const time = timeOf(comm.sent_at) ?? timeOf(comm.created_at);
      if (time !== null) responseTimes.push(time);
    }

    for (const interview of interviews) {
      responded = true;
      reachedIndex = Math.max(reachedIndex, pipelineRank(interviewStage(interview.stage)));
      const time = timeOf(interview.scheduled_at);
      if (time !== null) responseTimes.push(time);
    }

    // A rejection the employer gave (by status or outcome) is a response even without a dated event.
    if (!state.open && state.outcome === "rejected") responded = true;

    closingTimes.sort((a, b) => a - b);
    const closedAt = state.open ? null : (closingTimes[0] ?? appliedAt);

    const days = daysSince(lastActivityMs(app, latest, nowMs), nowMs) ?? 0;

    return {
      id: app.id,
      opportunityId: app.opportunity_id ?? null,
      providerId: app.provider_id ?? opp?.provider_id ?? null,
      company: (orgId && orgName.get(orgId)) || "Unknown company",
      title: opp?.title || "Untitled role",
      declineReason: app.decline_reason?.trim() || null,
      appliedAt,
      stage: state.stage,
      outcome: state.outcome,
      open: state.open,
      daysSinceActivity: days,
      closedAt,
      responded,
      responseAt: responseTimes.length > 0 ? Math.min(...responseTimes) : null,
      reachedIndex: Math.max(0, reachedIndex),
    };
  });
}

/** An application was open at time `t` if it had been applied for and had not yet closed. */
function openAt(fact: AppFact, t: number): boolean {
  if (fact.appliedAt === null || fact.appliedAt > t) return false;
  return fact.closedAt === null || fact.closedAt > t;
}

/* ------------------------------------------------------------------ */
/* Dashboard computation                                               */
/* ------------------------------------------------------------------ */

type DatedInterview = { row: InterviewRow; time: number };

export function computeDashboardBundle(
  input: DashboardInput,
  range: DateBounds,
  now: Date = new Date()
): DashboardBundle {
  const nowMs = now.getTime();
  const prev = previousPeriod(range);
  const facts = buildAppFacts(input, nowMs);

  const allInterviewTimes: DatedInterview[] = [];
  const heldInterviews: DatedInterview[] = [];
  for (const row of input.interviews) {
    const time = timeOf(row.scheduled_at);
    if (time === null) continue;
    allInterviewTimes.push({ row, time });
    if (isInterviewHeld(row.result, time, nowMs)) heldInterviews.push({ row, time });
  }
  const interviewsIn = (bounds: DateBounds) =>
    heldInterviews.filter((x) => inBounds(x.time, bounds)).length;

  const oppTimes = input.opportunities.map((o) => ({ row: o, time: timeOf(o.created_at) }));
  const oppsIn = (bounds: DateBounds) => oppTimes.filter((x) => inBounds(x.time, bounds));

  const scoredIn = (bounds: DateBounds) =>
    input.evaluations
      .filter((e) => inBounds(timeOf(e.evaluated_at), bounds))
      .map((e) => e.score)
      .filter((s): s is number => s != null && !Number.isNaN(Number(s)))
      .map(Number);

  const appsIn = (bounds: DateBounds) => facts.filter((f) => inBounds(f.appliedAt, bounds));
  const responseRateFor = (list: AppFact[]) =>
    rate(list.filter((f) => f.responded).length, list.length);

  const curApps = appsIn(range);
  const prevApps = appsIn(prev);
  const prevEnd = prev.end.getTime();

  const kpis: DashboardKpis = {
    openApplications: facts.filter((f) => f.open).length,
    openApplicationsPrev: facts.filter((f) => openAt(f, prevEnd)).length,
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
  const rangeOpps = oppsIn(range);
  const funnel: FunnelSummary = {
    steps: counts.map((step, index) => ({
      ...step,
      conversion: index === 0 ? null : rate(step.count, counts[index - 1].count),
    })),
    sourcing: {
      opportunitiesFound: rangeOpps.length,
      opportunitiesEvaluated: rangeOpps.filter((o) => evaluatedOppIds.has(o.row.id)).length,
      applied: curApps.length,
    },
  };

  const weeklyActivity = buildWeekly(facts, oppTimes, heldInterviews, range);
  const sourceEffectiveness = buildSources(input, facts, heldInterviews, range);

  /* Pipeline aging and attention. */
  const openFacts = facts.filter((f) => f.open);
  const pipelineAging: PipelineAgingRow[] = [...openFacts]
    .sort((a, b) => b.daysSinceActivity - a.daysSinceActivity)
    .slice(0, PIPELINE_AGING_LIMIT)
    .map((f) => ({
      applicationId: f.id,
      company: f.company,
      title: f.title,
      stage: f.stage,
      daysSinceActivity: f.daysSinceActivity,
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
    .filter((f) => isStalled(f.open, f.daysSinceActivity))
    .sort((a, b) => b.daysSinceActivity - a.daysSinceActivity)
    .map((f) => ({
      applicationId: f.id,
      company: f.company,
      title: f.title,
      stage: f.stage,
      daysSinceActivity: f.daysSinceActivity,
    }));

  const runTime = (run: Tables<"automation_runs">) => timeOf(run.started_at) ?? timeOf(run.created_at);
  const runErrors: RunError[] = input.failedRuns
    .map((run) => ({ run, status: run.status.trim().toLowerCase() }))
    .filter(({ status }) => status === FAILED_RUN_STATUS || status === PARTIAL_RUN_STATUS)
    .filter(({ run }) => {
      const t = runTime(run);
      return t !== null && t >= nowMs - ATTENTION_WINDOW_DAYS * DAY_MS && t <= nowMs;
    })
    .sort((a, b) => (runTime(b.run) ?? 0) - (runTime(a.run) ?? 0))
    .map(({ run, status }) => ({
      runId: run.id,
      startedAt: run.started_at ?? run.created_at,
      provider: (run.provider_id && providerName.get(run.provider_id)) || "Unknown provider",
      summary: run.summary,
      severity: status === FAILED_RUN_STATUS ? ("failed" as const) : ("partial" as const),
    }));

  /* Upcoming: future interviews and dated application events, chronological. */
  const upcoming: UpcomingItem[] = [];
  for (const { row, time } of allInterviewTimes) {
    if (time > nowMs) {
      upcoming.push({
        at: new Date(time).toISOString(),
        label: `Interview${row.stage ? ` (${row.stage})` : ""}`,
        href: `/interviews/${row.id}`,
      });
    }
  }
  for (const event of input.events) {
    const time = timeOf(event.event_at);
    if (time !== null && time > nowMs) {
      upcoming.push({
        at: new Date(time).toISOString(),
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
    automationRuns: input.runCount,
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
  interviews: DatedInterview[],
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
  heldInterviews: DatedInterview[],
  range: DateBounds
): SourceEffectiveness[] {
  const interviewedApps = new Set(heldInterviews.map((i) => i.row.application_id));
  const providerRows = new Map(input.providers.map((p) => [p.id, p]));

  const oppsInRange = input.opportunities.filter((o) => inBounds(timeOf(o.created_at), range));
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
    const withResponse = apps.filter((f) => f.responded).length;
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
    { evaluations: number; withApplication: number; offers: number; rejected: number; open: number; scores: number[] }
  >();
  for (const evaluation of input.evaluations) {
    if (!inBounds(timeOf(evaluation.evaluated_at), range)) continue;
    const bucket = scoreBucket(evaluation.score);
    const acc = scoreAcc.get(bucket) ?? {
      evaluations: 0,
      withApplication: 0,
      offers: 0,
      rejected: 0,
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
      else if (best === "rejected") acc.rejected += 1;
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
      rejected: acc.rejected,
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
    if (!inBounds(timeOf(opp.created_at), range)) continue;
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
    if (!inBounds(timeOf(interview.scheduled_at), range)) continue;
    const stage = interview.stage?.trim() ? interviewStage(interview.stage) : "unknown";
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

type QueryResult<T> = { data: T[] | null; error: PageError | null };

async function unwrapRows<T>(query: PromiseLike<QueryResult<T>>): Promise<T[]> {
  const { data, error } = await query;
  if (error) throw queryError(error);
  return data ?? [];
}

async function countRows(query: PromiseLike<{ count: number | null; error: PageError | null }>): Promise<number> {
  const { count, error } = await query;
  if (error) throw queryError(error);
  return count ?? 0;
}

/**
 * Reads every analytics table once. The result does not depend on the date range, so switching
 * ranges never fetches again; each range is computed from this in memory.
 */
export async function fetchRawAnalytics(): Promise<RawAnalytics> {
  const supabase = createClient();
  const attentionSince = new Date(Date.now() - ATTENTION_WINDOW_DAYS * DAY_MS).toISOString();

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
    runCount,
  ] = await Promise.all([
    fetchAll<ApplicationRow & KeysetRow>((after, limit) => {
      let query = supabase.from("applications").select(APPLICATION_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<EventRow & KeysetRow>((after, limit) => {
      let query = supabase.from("application_events").select(EVENT_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<InterviewRow & KeysetRow>((after, limit) => {
      let query = supabase.from("interviews").select(INTERVIEW_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<OpportunityRow & KeysetRow>((after, limit) => {
      let query = supabase.from("opportunities").select(OPPORTUNITY_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<EvaluationRow & KeysetRow>((after, limit) => {
      let query = supabase.from("evaluations").select(EVALUATION_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<CommunicationRow & KeysetRow>((after, limit) => {
      let query = supabase.from("communications").select(COMMUNICATION_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<OrganizationRow & KeysetRow>((after, limit) => {
      let query = supabase.from("organizations").select(ORGANIZATION_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    fetchAll<ProviderRow & KeysetRow>((after, limit) => {
      let query = supabase.from("providers").select(PROVIDER_COLUMNS).order("id").limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
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
    fetchAll<Tables<"automation_runs">>((after, limit) => {
      // Status is matched case-insensitively. Partial runs are warnings, failed runs are errors.
      let query = supabase
        .from("automation_runs")
        .select("*")
        .or(`status.ilike.${FAILED_RUN_STATUS},status.ilike.${PARTIAL_RUN_STATUS}`)
        .gte("created_at", attentionSince)
        .order("id")
        .limit(limit);
      if (after) query = query.gt("id", after);
      return query;
    }),
    countRows(supabase.from("automation_runs").select("id", { count: "exact", head: true })),
  ]);

  return {
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
    runCount,
  };
}
