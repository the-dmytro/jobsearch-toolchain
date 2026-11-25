"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/crm/error-state";

/**
 * Error boundary for dashboard pages. Next.js passes `retry`, which re-renders the
 * segment. The error itself is logged to the console and shown only as a friendly
 * message (see `friendlyError`).
 */
export default function DashboardError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto w-full max-w-lg py-8">
      <ErrorState
        title="This page couldn't load"
        error={error}
        onRetry={retry}
      />
    </div>
  );
}
