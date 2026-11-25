import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type EmptyStateProps = {
  /** Optional decorative icon, for example `<InboxIcon className="size-5" />`. Hidden from assistive tech. */
  icon?: ReactNode;
  /** Short headline that says what is missing, for example "No applications yet". */
  title: string;
  /** One or two sentences on what to do next. */
  description?: string;
  /** Optional call to action, usually a Button or Link. */
  action?: ReactNode;
  className?: string;
};

/**
 * Placeholder for a list, table or panel that has no data yet.
 *
 * Use it for "nothing here yet" and for filtered results that came back empty.
 * It is not announced by a live region, because it appears with the page. Use
 * `ErrorState` for failures and `TableSkeleton` / `CardSkeleton` while loading.
 *
 * @example
 * <EmptyState
 *   icon={<Briefcase className="size-5" />}
 *   title="No applications yet"
 *   description="Add one to start tracking your pipeline."
 *   action={<Button render={<Link href="/applications/new" />}>Add application</Button>}
 * />
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center",
        className
      )}
    >
      {icon ? (
        <span
          aria-hidden="true"
          className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"
        >
          {icon}
        </span>
      ) : null}
      <div className="space-y-1">
        <h2 className="text-base font-medium text-foreground">{title}</h2>
        {description ? (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
