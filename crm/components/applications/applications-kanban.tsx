"use client";

import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { changeApplicationStage } from "@/lib/actions/applications";
import { invalidateAfterMutation } from "@/lib/mutations";
import { CANONICAL_STAGES, normalizeStage } from "@/lib/stages";
import type { ApplicationWithJoins } from "./use-applications-query";

/** Board column for a stage. Withdrawn and ghosted applications sit in the closed column. */
function columnFor(raw: string | null | undefined): string {
  const stage = normalizeStage(raw);
  return (CANONICAL_STAGES as readonly string[]).includes(stage) ? stage : "declined";
}

function groupByStage(apps: ApplicationWithJoins[]) {
  const map = new Map<string, ApplicationWithJoins[]>();
  for (const s of CANONICAL_STAGES) map.set(s, []);
  for (const a of apps) {
    map.get(columnFor(a.current_stage))!.push(a);
  }
  return map;
}

function DroppableColumn({
  stage,
  children,
}: {
  stage: string;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-[200px] flex-col rounded-lg border bg-muted/20 ${isOver ? "ring-2 ring-ring" : ""}`}
    >
      {children}
    </div>
  );
}

function DraggableCard({ app }: { app: ApplicationWithJoins }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: app.id,
  });

  const style = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        opacity: isDragging ? 0.6 : 1,
      }
    : undefined;

  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes}>
      <Link href={`/applications/${app.id}`}>
        <Card className="cursor-grab active:cursor-grabbing hover:bg-muted/40">
          <CardHeader className="p-3 pb-1">
            <p className="text-sm font-medium leading-snug">
              {app.opportunities?.title ?? "Role"}
            </p>
            <p className="text-xs text-muted-foreground">
              {app.organizations?.name ?? "Company"}
            </p>
          </CardHeader>
          <CardContent className="p-3 pt-0 text-xs text-muted-foreground">
            {app.status}
          </CardContent>
        </Card>
      </Link>
    </div>
  );
}

export function ApplicationsKanban({ data }: { data: ApplicationWithJoins[] }) {
  const qc = useQueryClient();

  const grouped = useMemo(() => groupByStage(data), [data]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const mutation = useMutation({
    mutationFn: async (p: { applicationId: string; newStage: string }) => {
      const res = await changeApplicationStage(p);
      if (!res.ok) throw new Error(res.message);
    },
    onSuccess: (_data, variables) => {
      void invalidateAfterMutation(qc, { applicationId: variables.applicationId });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const appId = String(active.id);

    let targetStage: string | null = null;
    if (CANONICAL_STAGES.includes(over.id as (typeof CANONICAL_STAGES)[number])) {
      targetStage = over.id as string;
    } else {
      const overApp = data.find((a) => a.id === over.id);
      if (overApp) targetStage = columnFor(overApp.current_stage);
    }
    if (!targetStage) return;

    mutation.mutate({ applicationId: appId, newStage: targetStage });
  }

  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        {CANONICAL_STAGES.map((stage) => (
          <DroppableColumn key={stage} stage={stage}>
            <div className="border-b px-2 py-2 text-xs font-semibold capitalize">
              {stage.replace(/_/g, " ")}
            </div>
            <ScrollArea className="min-h-[320px] flex-1 p-2">
              <div className="flex flex-col gap-2">
                {(grouped.get(stage) ?? []).map((app) => (
                  <DraggableCard key={app.id} app={app} />
                ))}
              </div>
            </ScrollArea>
          </DroppableColumn>
        ))}
      </div>
    </DndContext>
  );
}
