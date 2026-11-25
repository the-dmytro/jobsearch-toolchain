"use client";

import { AlertTriangleIcon, RotateCcwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { friendlyError } from "@/lib/format";
import { cn } from "@/lib/utils";

export type ErrorStateProps = {
  /** Headline. Defaults to "Couldn't load this section". */
  title?: string;
  /**
   * The thrown or returned error. It is converted with `friendlyError`, so a raw
   * PostgREST object or stack trace is never shown.
   */
  error?: unknown;
  /** Optional fixed message used instead of the one derived from `error`. */
  description?: string;
  /** When given, a "Try again" button calls it. Pass the route `retry` or a refetch. */
  onRetry?: () => void;
  className?: string;
};

/**
 * Failure state for a section that could not load.
 *
 * Announced with `role="alert"`, so screen readers read it as soon as it appears.
 * Shows a plain-language message from `friendlyError`. The raw error is never
 * printed, so no JSON or database internals reach the page.
 *
 * @example
 * <ErrorState title="Applications failed to load" error={query.error} onRetry={() => query.refetch()} />
 */
export function ErrorState({
  title = "Couldn't load this section",
  error,
  description,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-danger/40 bg-card p-4 text-card-foreground",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">{title}</p>
          <p className="text-sm text-muted-foreground">
            {description ?? friendlyError(error)}
          </p>
        </div>
      </div>
      {onRetry ? (
        <div>
          <Button type="button" size="sm" variant="outline" onClick={onRetry}>
            <RotateCcwIcon aria-hidden="true" />
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  );
}
