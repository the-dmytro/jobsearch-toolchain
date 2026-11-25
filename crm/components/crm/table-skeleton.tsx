import { cn } from "@/lib/utils";

export type TableSkeletonProps = {
  /** Number of body rows to draw. Defaults to 5. */
  rows?: number;
  /** Number of columns to draw. Defaults to 4. */
  cols?: number;
  /** Accessible name for the loading region. Defaults to "Loading table". */
  label?: string;
  className?: string;
};

/**
 * Placeholder that matches a data table while its rows load.
 *
 * It is a `role="status"` live region, so the label is announced politely
 * without interrupting the user. Match `rows` and `cols` to the real table where
 * you can, to limit layout shift.
 *
 * @example
 * {query.isPending ? <TableSkeleton rows={8} cols={6} /> : <ApplicationsTable rows={query.data} />}
 */
export function TableSkeleton({
  rows = 5,
  cols = 4,
  label = "Loading table",
  className,
}: TableSkeletonProps) {
  const rowCount = Math.max(1, Math.floor(rows));
  const colCount = Math.max(1, Math.floor(cols));
  const grid = { gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))` };

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className={cn("w-full rounded-xl border bg-card p-3", className)}
    >
      <span className="sr-only">{label}…</span>
      <div aria-hidden="true" className="grid gap-3 border-b pb-3" style={grid}>
        {Array.from({ length: colCount }, (_, i) => (
          <div key={`h-${i}`} className="h-3 w-2/3 animate-pulse rounded bg-muted" />
        ))}
      </div>
      <div aria-hidden="true" className="space-y-3 pt-3">
        {Array.from({ length: rowCount }, (_, r) => (
          <div key={`r-${r}`} className="grid gap-3" style={grid}>
            {Array.from({ length: colCount }, (_, c) => (
              <div
                key={`c-${r}-${c}`}
                className={cn("h-4 animate-pulse rounded bg-muted", c === 0 ? "w-4/5" : "w-3/5")}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
