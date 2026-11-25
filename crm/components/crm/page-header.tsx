import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export type PageHeaderProps = {
  /** Page heading, rendered as the page's only <h1>. */
  title: string;
  /** One line of context under the title. Keep it short. */
  description?: string;
  /** Buttons or controls aligned to the right on wide screens and below the title on narrow ones. */
  actions?: ReactNode;
  /**
   * Total count shown as a badge beside the title, for example the number of
   * applications. It is formatted with `formatNumber` and set with tabular figures.
   */
  count?: number;
  className?: string;
};

/**
 * Title block for a dashboard page: heading, optional count, description and actions.
 *
 * It stacks on phones and places actions to the right from the `sm` breakpoint.
 * Use exactly one PageHeader per page, because it provides the <h1>.
 *
 * @example
 * <PageHeader title="Applications" count={42} description="Every role you are tracking." actions={<AddButton />} />
 */
export function PageHeader({
  title,
  description,
  actions,
  count,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className
      )}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="min-w-0 truncate text-2xl font-semibold tracking-tight">{title}</h1>
          {count !== undefined ? (
            <Badge variant="secondary" className="shrink-0 tabular-nums">
              {formatNumber(count)}
            </Badge>
          ) : null}
        </div>
        {description ? (
          <p className="text-sm text-pretty text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
