"use client";

import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { GripVerticalIcon, LoaderCircleIcon } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { formatDuration, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  BOARD_COLUMNS,
  BOARD_COLUMN_LABELS,
  type ApplicationRow,
  type BoardColumn,
} from "./application-model";
import { OutcomeBadge } from "./stage-badge";
import { useStageMove } from "./use-stage-move";

const SCREEN_READER_INSTRUCTIONS =
  "To move an application, press space or enter on its Move button. Then use the arrow keys to choose a stage, and press space or enter to drop it. Press escape to cancel.";

type DragData = { label: string; column: BoardColumn };

function isBoardColumn(value: unknown): value is BoardColumn {
  return typeof value === "string" && (BOARD_COLUMNS as readonly string[]).includes(value);
}

function readDragData(data: unknown): DragData | null {
  if (!data || typeof data !== "object") return null;
  const record = data as Partial<DragData>;
  if (typeof record.label !== "string" || !isBoardColumn(record.column)) return null;
  return { label: record.label, column: record.column };
}

/** Stage written to the server for a column. The Closed column records a decline. */
export function stageForColumn(column: BoardColumn): string {
  return column === "closed" ? "declined" : column;
}

/** Plain-language announcements for keyboard and screen reader users. */
export function describeDragStart(data: DragData): string {
  return `Picked up ${data.label}, in ${BOARD_COLUMN_LABELS[data.column]}. Use the arrow keys to choose a stage, then press space or enter to drop it. Press escape to cancel.`;
}

export function describeDragOver(data: DragData, overId: string | null | undefined): string {
  if (!isBoardColumn(overId)) return `${data.label} is not over a stage.`;
  return `${data.label} is over ${BOARD_COLUMN_LABELS[overId]}.`;
}

export function describeDragEnd(data: DragData, overId: string | null | undefined): string {
  if (!isBoardColumn(overId)) {
    return `${data.label} was dropped outside the board. Nothing changed.`;
  }
  if (overId === data.column) return `${data.label} stayed in ${BOARD_COLUMN_LABELS[overId]}.`;
  return `Dropped ${data.label} into ${BOARD_COLUMN_LABELS[overId]}. Saving the new stage.`;
}

export function describeDragCancel(data: DragData): string {
  return `Move cancelled. ${data.label} stays in ${BOARD_COLUMN_LABELS[data.column]}.`;
}

const announcements = {
  onDragStart({ active }: { active: { data: { current?: unknown } } }) {
    const data = readDragData(active.data.current);
    return data ? describeDragStart(data) : undefined;
  },
  onDragOver({ active, over }: { active: { data: { current?: unknown } }; over: { id: unknown } | null }) {
    const data = readDragData(active.data.current);
    return data ? describeDragOver(data, over ? String(over.id) : null) : undefined;
  },
  onDragEnd({ active, over }: { active: { data: { current?: unknown } }; over: { id: unknown } | null }) {
    const data = readDragData(active.data.current);
    return data ? describeDragEnd(data, over ? String(over.id) : null) : undefined;
  },
  onDragCancel({ active }: { active: { data: { current?: unknown } } }) {
    const data = readDragData(active.data.current);
    return data ? describeDragCancel(data) : undefined;
  },
};

function BoardCard({ row, pending }: { row: ApplicationRow; pending: boolean }) {
  const company = row.company || "Company unknown";
  const role = row.role || "Untitled role";
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, isDragging } =
    useDraggable({
      id: row.id,
      data: { label: `${company}, ${role}`, column: row.column } satisfies DragData,
      disabled: pending,
    });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <li
      ref={setNodeRef}
      style={style}
      aria-busy={pending || undefined}
      className={cn(
        "rounded-lg border bg-card p-3 shadow-xs",
        isDragging && "opacity-60 shadow-md"
      )}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <Link
            href={`/applications/${row.id}`}
            className="block rounded-sm text-sm font-medium leading-snug text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {role}
          </Link>
          <p className="truncate text-xs text-muted-foreground">{company}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            {row.column === "closed" ? <OutcomeBadge outcome={row.outcome} /> : null}
            {row.daysInStage !== null ? (
              <span className={cn("tabular-nums", row.stalled && "font-medium text-warning")}>
                {formatDuration(row.daysInStage)} in stage
                {row.stalled ? " · Stalled" : ""}
              </span>
            ) : null}
          </div>
          {pending ? (
            <p role="status" className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <LoaderCircleIcon aria-hidden="true" className="size-3.5 animate-spin motion-reduce:animate-none" />
              Saving…
            </p>
          ) : null}
        </div>
        <button
          type="button"
          ref={setActivatorNodeRef}
          {...listeners}
          {...attributes}
          disabled={pending}
          aria-label={`Move ${company} ${role}`}
          className="-mr-1 -mt-1 flex size-11 shrink-0 touch-none cursor-grab items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default disabled:opacity-50"
        >
          <GripVerticalIcon aria-hidden="true" className="size-4" />
        </button>
      </div>
    </li>
  );
}

function BoardColumnSection({
  column,
  count,
  children,
}: {
  column: BoardColumn;
  count: number;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column });
  const headingId = `board-${column}-heading`;
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={headingId}
      className={cn(
        "flex w-[16rem] shrink-0 snap-start flex-col rounded-xl border bg-muted/30 md:w-auto md:min-w-0",
        isOver && "ring-2 ring-ring"
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 id={headingId} className="text-sm font-semibold">
          {BOARD_COLUMN_LABELS[column]}
        </h2>
        <span className="text-xs tabular-nums text-muted-foreground">
          {formatNumber(count)}
          <span className="sr-only"> applications</span>
        </span>
      </header>
      <div className="flex flex-1 flex-col gap-2 p-2">{children}</div>
    </section>
  );
}

function groupByColumn(rows: ApplicationRow[]): Map<BoardColumn, ApplicationRow[]> {
  const groups = new Map<BoardColumn, ApplicationRow[]>(BOARD_COLUMNS.map((c) => [c, []]));
  for (const row of rows) groups.get(row.column)?.push(row);
  return groups;
}

/**
 * Stage board. Each card keeps its own link. Moving uses the card's Move button,
 * with a pointer or the keyboard. The board updates at once and rolls back if
 * the server refuses the change.
 */
export function ApplicationsKanban({ rows }: { rows: ApplicationRow[] }) {
  const { move, pendingIds } = useStageMove();
  const groups = useMemo(() => groupByColumn(rows), [rows]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  function onDragEnd(event: DragEndEvent) {
    const data = readDragData(event.active.data.current);
    const overId = event.over?.id;
    if (!data || !isBoardColumn(overId) || overId === data.column) return;
    move(String(event.active.id), stageForColumn(overId));
  }

  return (
    <DndContext
      sensors={sensors}
      onDragEnd={onDragEnd}
      accessibility={{ announcements, screenReaderInstructions: { draggable: SCREEN_READER_INSTRUCTIONS } }}
    >
      <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 md:mx-0 md:grid md:grid-cols-6 md:overflow-visible md:px-0">
        {BOARD_COLUMNS.map((column) => {
          const cards = groups.get(column) ?? [];
          return (
            <BoardColumnSection key={column} column={column} count={cards.length}>
              {cards.length === 0 ? (
                <p className="px-1 py-2 text-xs text-muted-foreground">No applications</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {cards.map((row) => (
                    <BoardCard key={row.id} row={row} pending={pendingIds.has(row.id)} />
                  ))}
                </ul>
              )}
            </BoardColumnSection>
          );
        })}
      </div>
    </DndContext>
  );
}
