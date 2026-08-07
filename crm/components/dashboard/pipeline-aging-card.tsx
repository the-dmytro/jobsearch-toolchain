import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { PipelineAging } from "@/lib/analytics";
import { normalizeStage } from "@/lib/stages";

type PipelineAgingCardProps = {
  pipeline: PipelineAging[];
};

export function PipelineAgingCard({ pipeline }: PipelineAgingCardProps) {
  const rows = pipeline.slice(0, 10);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline aging</CardTitle>
        <CardDescription>Open applications sorted by days in current stage</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No open applications</p>
        ) : (
          rows.map((row) => {
            const stale = (row.days_in_stage ?? 0) >= 14;
            return (
              <Link
                key={row.application_id}
                href={`/applications/${row.application_id}`}
                className="flex items-start justify-between gap-3 rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{row.opportunity_title}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {row.organization_name} · {normalizeStage(row.current_stage)}
                  </p>
                </div>
                <Badge variant={stale ? "destructive" : "secondary"}>
                  {row.days_in_stage ?? 0}d
                </Badge>
              </Link>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
