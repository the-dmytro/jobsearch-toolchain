import { Skeleton } from "@/components/ui/skeleton";

/**
 * Shown while a dashboard page streams in. It sits inside the dashboard shell, so
 * the header stays put and only the page body is replaced. The whole block is one
 * polite status region; the inner skeleton pieces are hidden from assistive tech.
 */
export default function DashboardLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Loading page"
      className="flex flex-col gap-6"
    >
      <span className="sr-only">Loading page…</span>
      <div aria-hidden="true" className="flex flex-col gap-6">
        <div className="space-y-2">
          <Skeleton className="h-7 w-48 max-w-full" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="space-y-3 rounded-xl border bg-card p-4 shadow-xs">
              <Skeleton className="h-3 w-1/2" />
              <Skeleton className="h-7 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          ))}
        </div>
        <div className="space-y-3 rounded-xl border bg-card p-4 shadow-xs">
          <Skeleton className="h-4 w-40" />
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
