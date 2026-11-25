import { cn } from "@/lib/utils";

export type CardSkeletonProps = {
  /** Number of text lines under the title bar. Defaults to 3. */
  lines?: number;
  /** Accessible name for the loading region. Defaults to "Loading". */
  label?: string;
  className?: string;
};

/**
 * Placeholder for a stat card, chart card or panel while its data loads.
 *
 * It is a `role="status"` live region with a short visually hidden label. Use it
 * for each card in a grid so the layout holds its size when the content arrives.
 *
 * @example
 * <CardSkeleton lines={4} label="Loading pipeline" />
 */
export function CardSkeleton({ lines = 3, label = "Loading", className }: CardSkeletonProps) {
  const count = Math.max(1, Math.floor(lines));
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className={cn(
        "flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-xs",
        className
      )}
    >
      <span className="sr-only">{label}…</span>
      <div aria-hidden="true" className="h-4 w-1/3 animate-pulse rounded bg-muted" />
      <div aria-hidden="true" className="space-y-2.5">
        {Array.from({ length: count }, (_, i) => (
          <div
            key={i}
            className={cn("h-3 animate-pulse rounded bg-muted", i === count - 1 ? "w-1/2" : "w-full")}
          />
        ))}
      </div>
    </div>
  );
}
