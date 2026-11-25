/**
 * Pure list logic for the applications screens: URL state, filters, row
 * decoration (role, company, days in stage) and the optimistic stage helpers.
 * Nothing here touches React or the network, so it is covered by unit tests.
 */
import {
  applicationOutcome,
  isOpenOutcome,
  isStageChangeEvent,
  isTerminal,
  normalizeStage,
  type StageOutcome,
} from "@/lib/stages";

import type {
  ApplicationWithJoins,
  ApplicationsBundle,
  StageEventRow,
} from "./use-applications-query";

const DAY_MS = 24 * 60 * 60 * 1000;

/** An application open longer than this is listed as stalled. Matches the dashboard rule. */
export const STALLED_DAYS = 14;

/** Board and stage-filter columns. Every terminal stage (declined, withdrawn, ghosted) is "closed". */
export const BOARD_COLUMNS = [
  "applied",
  "screening",
  "tech_interview",
  "onsite",
  "offer",
  "closed",
] as const;
export type BoardColumn = (typeof BOARD_COLUMNS)[number];

export const BOARD_COLUMN_LABELS: Record<BoardColumn, string> = {
  applied: "Applied",
  screening: "Screening",
  tech_interview: "Tech interview",
  onsite: "Onsite",
  offer: "Offer",
  closed: "Closed",
};

export const OUTCOME_FILTERS = ["active", "offer", "declined", "withdrawn", "ghosted"] as const;
export type OutcomeFilter = (typeof OUTCOME_FILTERS)[number];

export const OUTCOME_LABELS: Record<OutcomeFilter, string> = {
  active: "Active",
  offer: "Offer",
  declined: "Declined",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
};

export const PAGE_SIZES = [25, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];

export const LIST_VIEWS = ["table", "board"] as const;
export type ListView = (typeof LIST_VIEWS)[number];

export const SORT_IDS = ["company", "role", "stage", "applied", "days", "updated"] as const;
export type SortId = (typeof SORT_IDS)[number];

export const SORT_LABELS: Record<SortId, string> = {
  company: "Company",
  role: "Role",
  stage: "Stage",
  applied: "Applied",
  days: "Days in stage",
  updated: "Updated",
};

/** Sorts that start with the newest or largest value. Text and stage start ascending. */
const DESCENDING_FIRST: ReadonlySet<SortId> = new Set<SortId>(["applied", "days", "updated"]);

export type ListFilters = {
  q: string;
  stages: BoardColumn[];
  outcome: OutcomeFilter | null;
  /** Organization id, or null for every company. */
  company: string | null;
  stalled: boolean;
};

export type ListState = ListFilters & {
  sort: SortId;
  desc: boolean;
  page: number;
  pageSize: PageSize;
  view: ListView;
};

export const DEFAULT_SORT: SortId = "updated";
export const DEFAULT_PAGE_SIZE: PageSize = 25;

/** Read side of `URLSearchParams` or Next's read-only version of it. */
export type SearchParamsLike = {
  get(name: string): string | null;
  getAll(name: string): string[];
};

function defaultDescFor(sort: SortId): boolean {
  return DESCENDING_FIRST.has(sort);
}

function isOneOf<T extends string>(values: readonly T[], value: string | null): value is T {
  return value !== null && (values as readonly string[]).includes(value);
}

/**
 * Reads the list state from the URL. Unknown or malformed values fall back to
 * the defaults, so a hand-edited URL never breaks the screen.
 */
export function parseListState(params: SearchParamsLike): ListState {
  const stages = Array.from(new Set(params.getAll("stage"))).filter((value): value is BoardColumn =>
    isOneOf(BOARD_COLUMNS, value)
  );

  const sort = isOneOf(SORT_IDS, params.get("sort")) ? (params.get("sort") as SortId) : DEFAULT_SORT;
  const dir = params.get("dir");
  const desc = dir === "asc" ? false : dir === "desc" ? true : defaultDescFor(sort);

  const pageNumber = Number.parseInt(params.get("page") ?? "", 10);
  const sizeNumber = Number.parseInt(params.get("size") ?? "", 10);
  const pageSize = (PAGE_SIZES as readonly number[]).includes(sizeNumber)
    ? (sizeNumber as PageSize)
    : DEFAULT_PAGE_SIZE;

  const outcomeParam = params.get("outcome");
  const company = params.get("company")?.trim() ?? "";

  return {
    q: params.get("q") ?? "",
    stages,
    outcome: isOneOf(OUTCOME_FILTERS, outcomeParam) ? outcomeParam : null,
    company: company === "" ? null : company,
    stalled: params.get("stalled") === "1",
    sort,
    desc,
    page: Number.isInteger(pageNumber) && pageNumber >= 1 ? pageNumber : 1,
    pageSize,
    view: params.get("view") === "board" ? "board" : "table",
  };
}

/** Writes only the values that differ from the defaults, so clean URLs stay short. */
export function buildListSearchParams(state: ListState): URLSearchParams {
  const out = new URLSearchParams();
  const q = state.q.trim();
  if (q) out.set("q", q);
  for (const stage of state.stages) out.append("stage", stage);
  if (state.outcome) out.set("outcome", state.outcome);
  if (state.company) out.set("company", state.company);
  if (state.stalled) out.set("stalled", "1");
  if (state.sort !== DEFAULT_SORT || state.desc !== defaultDescFor(DEFAULT_SORT)) {
    out.set("sort", state.sort);
    out.set("dir", state.desc ? "desc" : "asc");
  }
  if (state.page > 1) out.set("page", String(state.page));
  if (state.pageSize !== DEFAULT_PAGE_SIZE) out.set("size", String(state.pageSize));
  if (state.view === "board") out.set("view", "board");
  return out;
}

export function hasActiveFilters(filters: ListFilters): boolean {
  return (
    filters.q.trim() !== "" ||
    filters.stages.length > 0 ||
    filters.outcome !== null ||
    filters.company !== null ||
    filters.stalled
  );
}

/** An application as the list shows it. Derived fields are computed once per data load. */
export type ApplicationRow = ApplicationWithJoins & {
  role: string;
  company: string;
  column: BoardColumn;
  stageOrder: number;
  outcome: StageOutcome;
  appliedMs: number | null;
  updatedMs: number | null;
  /** Whole days since the latest stage change, or since applying when there is none. */
  daysInStage: number | null;
  stalled: boolean;
};

function toMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

export function boardColumnFor(stage: string | null | undefined): BoardColumn {
  const normalized = normalizeStage(stage);
  return isTerminal(normalized) ? "closed" : (normalized as BoardColumn);
}

/** Latest stage-change time per application (epoch ms). */
export function latestStageChangeMs(events: readonly StageEventRow[]): Map<string, number> {
  const latest = new Map<string, number>();
  for (const event of events) {
    if (!isStageChangeEvent(event.event_type)) continue;
    const at = toMs(event.event_at) ?? toMs(event.created_at);
    if (at === null) continue;
    const previous = latest.get(event.application_id);
    if (previous === undefined || at > previous) latest.set(event.application_id, at);
  }
  return latest;
}

/** Adds role, company, column, outcome and days in stage to every application. */
export function decorateApplications(bundle: ApplicationsBundle, nowMs: number): ApplicationRow[] {
  const lastChange = latestStageChangeMs(bundle.events);
  return bundle.applications.map((app) => {
    const appliedMs = toMs(app.applied_at) ?? toMs(app.created_at);
    const base = lastChange.get(app.id) ?? appliedMs;
    const daysInStage = base === null ? null : Math.max(0, Math.floor((nowMs - base) / DAY_MS));
    const outcome = applicationOutcome(app);
    const column = boardColumnFor(app.current_stage);
    const open = isOpenOutcome(outcome) && !isTerminal(normalizeStage(app.current_stage));
    return {
      ...app,
      role: app.opportunities?.title ?? "",
      company: app.organizations?.name ?? "",
      column,
      stageOrder: BOARD_COLUMNS.indexOf(column),
      outcome,
      appliedMs,
      updatedMs: toMs(app.updated_at),
      daysInStage,
      stalled: open && daysInStage !== null && daysInStage > STALLED_DAYS,
    };
  });
}

export function matchesFilters(row: ApplicationRow, filters: ListFilters): boolean {
  const q = filters.q.trim().toLowerCase();
  if (q) {
    const found =
      row.company.toLowerCase().includes(q) ||
      row.role.toLowerCase().includes(q) ||
      (row.notes ?? "").toLowerCase().includes(q);
    if (!found) return false;
  }
  if (filters.stages.length > 0 && !filters.stages.includes(row.column)) return false;
  if (filters.outcome !== null && row.outcome !== filters.outcome) return false;
  if (filters.company !== null && row.organization_id !== filters.company) return false;
  if (filters.stalled && !row.stalled) return false;
  return true;
}

export function filterApplications(rows: readonly ApplicationRow[], filters: ListFilters) {
  return rows.filter((row) => matchesFilters(row, filters));
}

/** Companies that appear in the list, sorted by name, for the company filter. */
export function companyOptions(rows: readonly ApplicationRow[]): { id: string; name: string }[] {
  const byId = new Map<string, string>();
  for (const row of rows) {
    if (row.organization_id && !byId.has(row.organization_id)) {
      byId.set(row.organization_id, row.company || "Unnamed company");
    }
  }
  return Array.from(byId, ([id, name]) => ({ id, name })).sort((a, b) =>
    a.name.localeCompare(b.name, "en-GB")
  );
}

/**
 * Returns a copy of the bundle with the application moved to `toStage` and a
 * stage-change event added, so days in stage restart at once.
 */
export function applyStageChange(
  bundle: ApplicationsBundle,
  applicationId: string,
  toStage: string,
  optimisticEventId: string,
  nowIso: string
): ApplicationsBundle {
  return {
    applications: bundle.applications.map((app) =>
      app.id === applicationId ? { ...app, current_stage: toStage } : app
    ),
    events: [
      ...bundle.events,
      {
        id: optimisticEventId,
        application_id: applicationId,
        event_type: "stage_change",
        event_at: nowIso,
        created_at: nowIso,
        title: `Stage → ${toStage}`,
        metadata: { to_stage: toStage },
      },
    ],
  };
}

/** Undoes `applyStageChange` after the server refused the move. */
export function revertStageChange(
  bundle: ApplicationsBundle,
  applicationId: string,
  previousStage: string | null,
  optimisticEventId: string
): ApplicationsBundle {
  return {
    applications: bundle.applications.map((app) =>
      app.id === applicationId ? { ...app, current_stage: previousStage } : app
    ),
    events: bundle.events.filter((event) => event.id !== optimisticEventId),
  };
}
