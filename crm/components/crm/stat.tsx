import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatProps = {
  /** Metric name, for example "Active applications". */
  label: string;
  /** The figure. A string from `formatNumber` / `formatPercent` / etc. is typical. */
  value: ReactNode;
  /** Context under the value, for example "+4 this week". */
  sub?: ReactNode;
  /** Optional icon shown beside the label. Hidden from assistive tech. */
  icon?: ReactNode;
  /**
   * Apply `tabular-nums` to the value (default true). Digits then have equal
   * width, so figures in a row of stats or a column line up. Turn it off for a
   * prose-like hero number where proportional figures read better.
   */
  tabular?: boolean;
  className?: string;
};

/**
 * Label, value and optional sub-label, used for KPI tiles and summary rows.
 *
 * Renders as a description list, so each label is paired with its value for
 * screen readers. Keep the value short (a number or a few words). Put the unit
 * or comparison in `sub`.
 *
 * Tabular figures: the default `tabular` applies `tabular-nums`, which is the
 * right choice when stats sit side by side or when numbers change in place.
 * For numbers inside a table use `tabular-nums` on the cell.
 *
 * @example
 * <Stat label="Interviews" value={formatNumber(7)} sub="3 scheduled" />
 */
export function Stat({ label, value, sub, icon, tabular = true, className }: StatProps) {
  return (
    <dl className={cn("flex min-w-0 flex-col gap-1", className)}>
      <dt className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        {icon ? (
          <span aria-hidden="true" className="inline-flex size-3.5 items-center justify-center">
            {icon}
          </span>
        ) : null}
        <span className="truncate">{label}</span>
      </dt>
      <dd
        className={cn(
          "text-2xl font-semibold tracking-tight text-foreground",
          tabular && "tabular-nums"
        )}
      >
        {value}
      </dd>
      {sub ? <dd className="text-xs text-muted-foreground">{sub}</dd> : null}
    </dl>
  );
}
