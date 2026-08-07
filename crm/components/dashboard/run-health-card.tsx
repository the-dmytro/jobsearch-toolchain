import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Tables } from "@/types/database.types";

type RunHealthCardProps = {
  runs: Tables<"automation_runs">[];
  runEvents: Tables<"automation_run_events">[];
};

export function RunHealthCard({ runs, runEvents }: RunHealthCardProps) {
  const completed = runs.filter((r) => r.status === "completed").length;
  const successRate =
    runs.length > 0 ? Math.round((completed / runs.length) * 100) : 0;
  const recentErrors = runEvents.filter((e) => e.severity === "error").slice(0, 3);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Run health</CardTitle>
        <CardDescription>
          {successRate}% success across recent automation runs
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs yet</p>
        ) : (
          runs.slice(0, 5).map((run) => (
            <Link
              key={run.id}
              href={`/runs/${run.id}`}
              className="flex items-center justify-between rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{run.run_key ?? run.id.slice(0, 8)}</p>
                <p className="text-xs text-muted-foreground">
                  src {run.source_items_count} · opp {run.opportunities_count} · eval{" "}
                  {run.evaluations_count}
                </p>
              </div>
              <Badge variant={run.status === "completed" ? "secondary" : "destructive"}>
                {run.status}
              </Badge>
            </Link>
          ))
        )}
        {recentErrors.length > 0 ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs">
            <p className="font-medium text-destructive">Recent errors</p>
            <ul className="mt-1 space-y-1 text-muted-foreground">
              {recentErrors.map((event) => (
                <li key={event.id}>{event.message ?? event.event_type}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
