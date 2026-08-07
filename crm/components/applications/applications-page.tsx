"use client";

import { LayoutGrid, TableIcon } from "lucide-react";
import { useState } from "react";
import { ApplicationsKanban } from "@/components/applications/applications-kanban";
import { ApplicationsTable } from "@/components/applications/applications-table";
import { useApplicationsQuery } from "@/components/applications/use-applications-query";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ApplicationsPage() {
  const { data, isLoading, error } = useApplicationsQuery();
  const [mode, setMode] = useState<"list" | "board">("list");

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  if (error) {
    return (
      <p className="text-destructive">
        {error instanceof Error ? error.message : "Failed to load"}
      </p>
    );
  }

  const rows = data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Applications</h1>
          <p className="text-sm text-muted-foreground">{rows.length} total</p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant={mode === "list" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("list")}
          >
            <TableIcon className="mr-1 size-4" />
            List
          </Button>
          <Button
            type="button"
            variant={mode === "board" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("board")}
          >
            <LayoutGrid className="mr-1 size-4" />
            Board
          </Button>
        </div>
      </div>
      {mode === "list" ? (
        <ApplicationsTable data={rows} />
      ) : (
        <ApplicationsKanban data={rows} />
      )}
    </div>
  );
}
