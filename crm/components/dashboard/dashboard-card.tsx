import { useId, type ReactNode } from "react";

import { CardSkeleton } from "@/components/crm/card-skeleton";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Load state for one card. Each card gets its own, so one failed query does not blank the page. */
export type CardStatus = {
  loading: boolean;
  error?: unknown;
  onRetry?: () => void;
};

export type DashboardCardProps = {
  /** Card heading. Also used for the loading and error copy. */
  title: string;
  /** One line that says what the card shows, and its unit. */
  description: string;
  status: CardStatus;
  /** True when the data loaded but there is nothing to show. */
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
  /** Controls or text under the content, for example a "show all" toggle. */
  footer?: ReactNode;
  children?: ReactNode;
};

/**
 * Shared frame for every dashboard and insights card: heading, one-line description,
 * and the loading, error and empty states. Loading shows a CardSkeleton in place of the
 * whole card, so the grid keeps its shape while data arrives.
 */
export function DashboardCard({
  title,
  description,
  status,
  isEmpty = false,
  emptyTitle = "Nothing to show yet",
  emptyDescription,
  className,
  footer,
  children,
}: DashboardCardProps) {
  const headingId = useId();

  if (status.loading) {
    return <CardSkeleton lines={4} label={`Loading ${title.toLowerCase()}`} className={className} />;
  }

  if (status.error) {
    return (
      <ErrorState
        title={`Couldn't load ${title.toLowerCase()}`}
        error={status.error}
        onRetry={status.onRetry}
        className={className}
      />
    );
  }

  return (
    <section aria-labelledby={headingId} className={cn("min-w-0", className)}>
      <Card className="h-full">
        <CardHeader>
          <h2 id={headingId} className="font-heading text-base leading-snug font-medium">
            {title}
          </h2>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="min-w-0 space-y-4">
          {isEmpty ? (
            <EmptyState
              title={emptyTitle}
              description={emptyDescription}
              className="border-0 px-2 py-6"
            />
          ) : (
            children
          )}
          {footer && !isEmpty ? footer : null}
        </CardContent>
      </Card>
    </section>
  );
}
