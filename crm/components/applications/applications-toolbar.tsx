"use client";

import { FilterXIcon } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  BOARD_COLUMNS,
  BOARD_COLUMN_LABELS,
  OUTCOME_FILTERS,
  OUTCOME_LABELS,
  STALLED_DAYS,
  hasActiveFilters,
  type BoardColumn,
  type ListFilters,
  type OutcomeFilter,
} from "./application-model";

const SEARCH_DEBOUNCE_MS = 300;

export type ApplicationsToolbarProps = {
  filters: ListFilters;
  companies: { id: string; name: string }[];
  /** Applications that match the filters. */
  matchCount: number;
  /** Applications in the list before filtering. */
  totalCount: number;
  disabled?: boolean;
  onChange: (patch: Partial<ListFilters>) => void;
  onClear: () => void;
};

const SELECT_CLASS =
  "h-9 w-full rounded-md border bg-background px-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Filters shared by the table and the board. Search is debounced so typing does
 * not write the URL on every key. Every control is labelled, and toggles report
 * their state with aria-pressed.
 */
export function ApplicationsToolbar({
  filters,
  companies,
  matchCount,
  totalCount,
  disabled = false,
  onChange,
  onClear,
}: ApplicationsToolbarProps) {
  const searchId = useId();
  const outcomeId = useId();
  const companyId = useId();
  const stageLegendId = useId();

  const [draft, setDraft] = useState(filters.q);
  const [syncedQ, setSyncedQ] = useState(filters.q);

  // Follow the URL when it changes from outside (for example "Clear filters").
  if (filters.q !== syncedQ) {
    setSyncedQ(filters.q);
    setDraft(filters.q);
  }

  useEffect(() => {
    if (draft === filters.q) return;
    const timer = setTimeout(() => onChange({ q: draft }), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `onChange` is recreated on each render; the timer only depends on the draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  function toggleStage(column: BoardColumn) {
    const selected = filters.stages.includes(column);
    const stages = BOARD_COLUMNS.filter((c) =>
      c === column ? !selected : filters.stages.includes(c)
    );
    onChange({ stages });
  }

  const active = hasActiveFilters(filters);
  const countText =
    matchCount === totalCount
      ? `${formatNumber(totalCount)} applications`
      : `${formatNumber(matchCount)} of ${formatNumber(totalCount)} applications`;

  return (
    <div className="space-y-3 rounded-xl border bg-card p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-1">
          <label htmlFor={searchId} className="text-xs font-medium text-muted-foreground">
            Search
          </label>
          <Input
            id={searchId}
            type="search"
            value={draft}
            disabled={disabled}
            placeholder="Company, role or notes"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onChange({ q: draft });
            }}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor={outcomeId} className="text-xs font-medium text-muted-foreground">
            Outcome
          </label>
          <select
            id={outcomeId}
            className={SELECT_CLASS}
            disabled={disabled}
            value={filters.outcome ?? ""}
            onChange={(event) =>
              onChange({ outcome: event.target.value === "" ? null : (event.target.value as OutcomeFilter) })
            }
          >
            <option value="">Any outcome</option>
            {OUTCOME_FILTERS.map((outcome) => (
              <option key={outcome} value={outcome}>
                {OUTCOME_LABELS[outcome]}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor={companyId} className="text-xs font-medium text-muted-foreground">
            Company
          </label>
          <select
            id={companyId}
            className={SELECT_CLASS}
            disabled={disabled}
            value={filters.company ?? ""}
            onChange={(event) => onChange({ company: event.target.value === "" ? null : event.target.value })}
          >
            <option value="">All companies</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span id={stageLegendId} className="text-xs font-medium text-muted-foreground">
            Stage
          </span>
          <div role="group" aria-labelledby={stageLegendId} className="flex flex-wrap gap-1.5">
            {BOARD_COLUMNS.map((column) => {
              const pressed = filters.stages.includes(column);
              return (
                <button
                  key={column}
                  type="button"
                  aria-pressed={pressed}
                  disabled={disabled}
                  onClick={() => toggleStage(column)}
                  className={cn(
                    "min-h-11 rounded-full border px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:min-h-7 md:px-2.5",
                    pressed
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background text-foreground hover:bg-muted"
                  )}
                >
                  {BOARD_COLUMN_LABELS[column]}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            aria-pressed={filters.stalled}
            disabled={disabled}
            onClick={() => onChange({ stalled: !filters.stalled })}
            className={cn(
              "min-h-11 rounded-full border px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:min-h-7 md:px-2.5",
              filters.stalled
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background text-foreground hover:bg-muted"
            )}
          >
            Stalled over {STALLED_DAYS} days
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <p role="status" aria-live="polite" className="text-sm tabular-nums text-muted-foreground">
            {countText}
          </p>
          {active ? (
            <Button type="button" variant="outline" size="sm" onClick={onClear}>
              <FilterXIcon aria-hidden="true" />
              Clear filters
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
