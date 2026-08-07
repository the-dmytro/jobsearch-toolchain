import { isFuture, subMilliseconds } from "date-fns";

import { createClient } from "@/lib/supabase/client";
import type { Tables, Views } from "@/types/database.types";

export type FunnelSummary = Views<"v_funnel_summary">;
export type WeeklyActivity = Views<"v_weekly_activity">;
export type SourceEffectiveness = Views<"v_source_effectiveness">;
export type PipelineAging = Views<"v_pipeline_aging">;
export type ScoreOutcome = Views<"v_score_outcomes">;

export type UpcomingItem = {
  at: string;
  label: string;
  href: string;
};

export type DashboardKpis = {
  openApplications: number;
  appliedInRange: number;
  appliedPrevPeriod: number;
  responseRate: number;
  responseRatePrev: number;
  interviewsInRange: number;
  interviewsPrev: number;
  newOpportunities: number;
  newOpportunitiesPrev: number;
  avgScore: number;
  avgScorePrev: number;
};

export type DateBounds = {
  start: Date;
  end: Date;
};

export type DashboardBundle = {
  kpis: DashboardKpis;
  weeklyActivity: WeeklyActivity[];
  funnel: FunnelSummary | null;
  sourceEffectiveness: SourceEffectiveness[];
  pipelineAging: PipelineAging[];
  upcoming: UpcomingItem[];
  runs: Tables<"automation_runs">[];
  runEvents: Tables<"automation_run_events">[];
};

export type OutcomeBreakdown = {
  outcome: string;
  count: number;
};

export type DeclineReason = {
  reason: string;
  count: number;
};

export type CompensationBySeniority = {
  seniority: string;
  avgMin: number;
  avgMax: number;
  count: number;
};

export type InterviewOutcome = {
  stage: string;
  result: string;
  count: number;
};

export type InsightsBundle = {
  scoreOutcomes: ScoreOutcome[];
  outcomeBreakdown: OutcomeBreakdown[];
  declineReasons: DeclineReason[];
  compensationBySeniority: CompensationBySeniority[];
  interviewOutcomes: InterviewOutcome[];
};

function toIso(date: Date): string {
  return date.toISOString();
}

function previousPeriod(range: DateBounds): DateBounds {
  const durationMs = range.end.getTime() - range.start.getTime();
  return {
    start: subMilliseconds(range.start, durationMs + 1),
    end: subMilliseconds(range.start, 1),
  };
}

function inRange(value: string | null | undefined, range: DateBounds): boolean {
  if (!value) return false;
  const ts = new Date(value).getTime();
  return ts >= range.start.getTime() && ts <= range.end.getTime();
}

function isOpenApplication(app: Tables<"applications">): boolean {
  const status = (app.status ?? "active").toLowerCase();
  const outcome = (app.outcome ?? "").toLowerCase();
  const stage = (app.current_stage ?? "").toLowerCase();
  if (["declined", "rejected", "withdrawn", "closed"].includes(status)) return false;
  if (["declined", "rejected", "withdrawn"].includes(outcome)) return false;
  if (["declined", "rejected", "withdrawn"].includes(stage)) return false;
  return true;
}

function responseRateFor(
  applications: Tables<"applications">[],
  events: Tables<"application_events">[],
  range: DateBounds
): number {
  const inWindow = applications.filter((app) =>
    inRange(app.applied_at ?? app.created_at, range)
  );
  if (inWindow.length === 0) return 0;
  const responded = new Set(
    events
      .filter((event) =>
        ["reply", "interview_invite", "response"].includes(event.event_type.toLowerCase())
      )
      .map((event) => event.application_id)
  );
  const hit = inWindow.filter((app) => responded.has(app.id)).length;
  return Math.round((hit / inWindow.length) * 100);
}

function averageScore(
  evaluations: Array<{ score: number | null; evaluated_at: string }>,
  range: DateBounds
): number {
  const scores = evaluations
    .filter((row) => inRange(row.evaluated_at, range))
    .map((row) => row.score)
    .filter((score): score is number => score != null && !Number.isNaN(Number(score)))
    .map(Number);
  if (scores.length === 0) return 0;
  return Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
}

function countMap(values: Array<string | null | undefined>): Map<string, number> {
  const map = new Map<string, number>();
  for (const value of values) {
    const key = (value ?? "unknown").trim() || "unknown";
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  return map;
}

export async function fetchDashboardBundle(range: DateBounds): Promise<DashboardBundle> {
  const supabase = createClient();
  const prev = previousPeriod(range);
  const startIso = toIso(range.start);
  const endIso = toIso(range.end);

  const [
    funnelRes,
    weeklyRes,
    sourceRes,
    agingRes,
    appsRes,
    eventsRes,
    interviewsRes,
    oppsRes,
    evalsRes,
    runsRes,
    runEventsRes,
  ] = await Promise.all([
    supabase.from("v_funnel_summary").select("*").maybeSingle(),
    supabase
      .from("v_weekly_activity")
      .select("*")
      .gte("week_start", startIso.slice(0, 10))
      .lte("week_start", endIso.slice(0, 10))
      .order("week_start", { ascending: true }),
    supabase.from("v_source_effectiveness").select("*"),
    supabase
      .from("v_pipeline_aging")
      .select("*")
      .order("days_in_stage", { ascending: false })
      .limit(25),
    supabase.from("applications").select("*"),
    supabase.from("application_events").select("*"),
    supabase.from("interviews").select("*").order("scheduled_at", { ascending: true }),
    supabase.from("opportunities").select("id, created_at"),
    supabase.from("evaluations").select("id, score, evaluated_at"),
    supabase
      .from("automation_runs")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(10),
    supabase
      .from("automation_run_events")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(50),
  ]);

  const errors = [
    funnelRes.error,
    weeklyRes.error,
    sourceRes.error,
    agingRes.error,
    appsRes.error,
    eventsRes.error,
    interviewsRes.error,
    oppsRes.error,
    evalsRes.error,
    runsRes.error,
    runEventsRes.error,
  ].filter(Boolean);
  if (errors.length) {
    throw new Error(errors[0]?.message ?? "Failed to load dashboard analytics");
  }

  const applications = (appsRes.data ?? []) as Tables<"applications">[];
  const events = (eventsRes.data ?? []) as Tables<"application_events">[];
  const interviews = (interviewsRes.data ?? []) as Tables<"interviews">[];
  const opportunities = oppsRes.data ?? [];
  const evaluations = evalsRes.data ?? [];

  const kpis: DashboardKpis = {
    openApplications: applications.filter(isOpenApplication).length,
    appliedInRange: applications.filter((app) =>
      inRange(app.applied_at ?? app.created_at, range)
    ).length,
    appliedPrevPeriod: applications.filter((app) =>
      inRange(app.applied_at ?? app.created_at, prev)
    ).length,
    responseRate: responseRateFor(applications, events, range),
    responseRatePrev: responseRateFor(applications, events, prev),
    interviewsInRange: interviews.filter((row) =>
      inRange(row.scheduled_at ?? row.completed_at ?? row.created_at, range)
    ).length,
    interviewsPrev: interviews.filter((row) =>
      inRange(row.scheduled_at ?? row.completed_at ?? row.created_at, prev)
    ).length,
    newOpportunities: opportunities.filter((row) => inRange(row.created_at, range)).length,
    newOpportunitiesPrev: opportunities.filter((row) => inRange(row.created_at, prev)).length,
    avgScore: averageScore(evaluations, range),
    avgScorePrev: averageScore(evaluations, prev),
  };

  const upcoming: UpcomingItem[] = [];
  for (const interview of interviews) {
    if (interview.scheduled_at && isFuture(new Date(interview.scheduled_at))) {
      upcoming.push({
        at: interview.scheduled_at,
        label: `Interview${interview.stage ? ` (${interview.stage})` : ""}`,
        href: `/interviews/${interview.id}`,
      });
    }
  }
  for (const event of events) {
    if (event.event_at && isFuture(new Date(event.event_at))) {
      upcoming.push({
        at: event.event_at,
        label: event.title ?? event.event_type,
        href: `/applications/${event.application_id}`,
      });
    }
  }
  upcoming.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());

  return {
    kpis,
    weeklyActivity: (weeklyRes.data ?? []) as WeeklyActivity[],
    funnel: (funnelRes.data as FunnelSummary | null) ?? null,
    sourceEffectiveness: (sourceRes.data ?? []) as SourceEffectiveness[],
    pipelineAging: (agingRes.data ?? []) as PipelineAging[],
    upcoming: upcoming.slice(0, 12),
    runs: (runsRes.data ?? []) as Tables<"automation_runs">[],
    runEvents: (runEventsRes.data ?? []) as Tables<"automation_run_events">[],
  };
}

export async function fetchInsightsBundle(range: DateBounds): Promise<InsightsBundle> {
  const supabase = createClient();
  const startIso = toIso(range.start);
  const endIso = toIso(range.end);

  const [scoreRes, appsRes, oppsRes, interviewsRes] = await Promise.all([
    supabase.from("v_score_outcomes").select("*"),
    supabase
      .from("applications")
      .select("id, outcome, decline_reason, applied_at, created_at, updated_at")
      .gte("updated_at", startIso)
      .lte("updated_at", endIso),
    supabase
      .from("opportunities")
      .select("id, seniority, compensation_min, compensation_max, created_at")
      .gte("created_at", startIso)
      .lte("created_at", endIso),
    supabase
      .from("interviews")
      .select("id, stage, result, scheduled_at, completed_at, created_at")
      .gte("created_at", startIso)
      .lte("created_at", endIso),
  ]);

  const errors = [scoreRes.error, appsRes.error, oppsRes.error, interviewsRes.error].filter(
    Boolean
  );
  if (errors.length) {
    throw new Error(errors[0]?.message ?? "Failed to load insights analytics");
  }

  const applications = appsRes.data ?? [];
  const opportunities = oppsRes.data ?? [];
  const interviews = interviewsRes.data ?? [];

  const outcomeCounts = countMap(
    applications
      .map((row) => row.outcome)
      .filter((value): value is string => Boolean(value && value.trim()))
  );
  const outcomeBreakdown = Array.from(outcomeCounts.entries())
    .map(([outcome, count]) => ({ outcome, count }))
    .sort((a, b) => b.count - a.count);

  const declineCounts = countMap(
    applications
      .map((row) => row.decline_reason)
      .filter((value): value is string => Boolean(value && value.trim()))
  );
  const declineReasons = Array.from(declineCounts.entries())
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);

  const compensationBuckets = new Map<
    string,
    { minSum: number; maxSum: number; minCount: number; maxCount: number; count: number }
  >();
  for (const opp of opportunities) {
    const seniority = (opp.seniority ?? "unspecified").toLowerCase();
    const bucket = compensationBuckets.get(seniority) ?? {
      minSum: 0,
      maxSum: 0,
      minCount: 0,
      maxCount: 0,
      count: 0,
    };
    bucket.count += 1;
    if (opp.compensation_min != null) {
      bucket.minSum += Number(opp.compensation_min);
      bucket.minCount += 1;
    }
    if (opp.compensation_max != null) {
      bucket.maxSum += Number(opp.compensation_max);
      bucket.maxCount += 1;
    }
    compensationBuckets.set(seniority, bucket);
  }
  const compensationBySeniority = Array.from(compensationBuckets.entries())
    .map(([seniority, bucket]) => ({
      seniority,
      avgMin: bucket.minCount ? Math.round(bucket.minSum / bucket.minCount) : 0,
      avgMax: bucket.maxCount ? Math.round(bucket.maxSum / bucket.maxCount) : 0,
      count: bucket.count,
    }))
    .sort((a, b) => b.count - a.count);

  const interviewCounts = new Map<string, number>();
  for (const interview of interviews) {
    const stage = (interview.stage ?? "unknown").toLowerCase();
    const result = (interview.result ?? "pending").toLowerCase();
    const key = `${stage}::${result}`;
    interviewCounts.set(key, (interviewCounts.get(key) ?? 0) + 1);
  }
  const interviewOutcomes = Array.from(interviewCounts.entries())
    .map(([key, count]) => {
      const [stage, result] = key.split("::");
      return { stage, result, count };
    })
    .sort((a, b) => b.count - a.count);

  return {
    scoreOutcomes: (scoreRes.data ?? []) as ScoreOutcome[],
    outcomeBreakdown,
    declineReasons,
    compensationBySeniority,
    interviewOutcomes,
  };
}
