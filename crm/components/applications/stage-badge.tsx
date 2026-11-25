import { Badge } from "@/components/ui/badge";
import type { StageOutcome } from "@/lib/stages";
import { cn } from "@/lib/utils";

import { BOARD_COLUMN_LABELS, OUTCOME_LABELS, type BoardColumn } from "./application-model";

/** Stage name as a badge. The text carries the meaning; colour is secondary. */
export function StageBadge({ column, className }: { column: BoardColumn; className?: string }) {
  return (
    <Badge
      variant={column === "closed" ? "outline" : "secondary"}
      className={cn("font-medium", className)}
    >
      {BOARD_COLUMN_LABELS[column]}
    </Badge>
  );
}

const OUTCOME_CLASS: Record<StageOutcome, string> = {
  offer: "border-success/40 text-success",
  declined: "border-danger/40 text-danger",
  withdrawn: "border-border text-muted-foreground",
  ghosted: "border-border text-muted-foreground",
  active: "border-info/40 text-info",
};

/** Outcome label for an application that is no longer open, or an offer. */
export function OutcomeBadge({ outcome, className }: { outcome: StageOutcome; className?: string }) {
  const label = OUTCOME_LABELS[outcome];
  return (
    <Badge variant="outline" className={cn("font-medium", OUTCOME_CLASS[outcome], className)}>
      {label}
    </Badge>
  );
}
