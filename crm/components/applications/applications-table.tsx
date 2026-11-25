"use client";

import {
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_basic,
  sortFn_text,
  tableFeatures,
  useTable,
  type Updater,
} from "@tanstack/react-table";
import { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon } from "lucide-react";
import Link from "next/link";
import { useId, useMemo } from "react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatDuration, formatNumber, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  PAGE_SIZES,
  SORT_LABELS,
  type ApplicationRow,
  type PageSize,
  type SortId,
} from "./application-model";
import { StageBadge } from "./stage-badge";

// Sorting and pagination run in TanStack. The page keeps the state in the URL.
const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { text: sortFn_text, basic: sortFn_basic },
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});
const columnHelper = createColumnHelper<typeof features, ApplicationRow>();

function DateCell({ ms }: { ms: number | null }) {
  if (ms === null) return <span className="text-muted-foreground">—</span>;
  return (
    <time dateTime={new Date(ms).toISOString()} title={formatRelative(ms)} className="whitespace-nowrap">
      {formatDate(ms)}
    </time>
  );
}

const columns = columnHelper.columns([
  columnHelper.accessor((row) => row.role, {
    id: "role",
    header: SORT_LABELS.role,
    sortFn: "text",
    cell: ({ row }) => (
      <Link
        href={`/applications/${row.original.id}`}
        className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
      >
        {row.original.role || "Untitled role"}
      </Link>
    ),
  }),
  columnHelper.accessor((row) => row.company, {
    id: "company",
    header: SORT_LABELS.company,
    sortFn: "text",
    cell: ({ row }) => row.original.company || "—",
  }),
  columnHelper.accessor((row) => row.stageOrder, {
    id: "stage",
    header: SORT_LABELS.stage,
    sortFn: "basic",
    cell: ({ row }) => <StageBadge column={row.original.column} />,
  }),
  columnHelper.accessor((row) => row.appliedMs ?? undefined, {
    id: "applied",
    header: SORT_LABELS.applied,
    sortFn: "basic",
    sortUndefined: "last",
    cell: ({ row }) => <DateCell ms={row.original.appliedMs} />,
  }),
  columnHelper.accessor((row) => row.daysSinceActivity ?? undefined, {
    id: "days",
    header: SORT_LABELS.days,
    sortFn: "basic",
    sortUndefined: "last",
    cell: ({ row }) => (
      <span className={cn("tabular-nums", row.original.stalled && "font-medium text-warning")}>
        {formatDuration(row.original.daysSinceActivity)}
        {row.original.stalled ? <span className="ml-1 text-xs">· Stalled</span> : null}
      </span>
    ),
  }),
  columnHelper.accessor((row) => row.updatedMs ?? undefined, {
    id: "updated",
    header: SORT_LABELS.updated,
    sortFn: "basic",
    sortUndefined: "last",
    cell: ({ row }) => <DateCell ms={row.original.updatedMs} />,
  }),
]);

type Sort = { id: SortId; desc: boolean };

export type ApplicationsTableProps = {
  /** Rows that already match the filters. Sorting and paging happen here. */
  rows: ApplicationRow[];
  sort: Sort;
  onSortChange: (sort: Sort) => void;
  /** Zero-based page index. */
  pageIndex: number;
  pageSize: PageSize;
  onPageIndexChange: (pageIndex: number) => void;
  onPageSizeChange: (pageSize: PageSize) => void;
};

function resolveUpdater<T>(updater: Updater<T>, previous: T): T {
  return typeof updater === "function" ? (updater as (old: T) => T)(previous) : updater;
}

function ariaSortFor(sorted: false | "asc" | "desc"): "ascending" | "descending" | "none" {
  if (sorted === "asc") return "ascending";
  if (sorted === "desc") return "descending";
  return "none";
}

function SortIndicator({ sorted }: { sorted: false | "asc" | "desc" }) {
  const Icon = sorted === "asc" ? ArrowUpIcon : sorted === "desc" ? ArrowDownIcon : ArrowUpDownIcon;
  return <Icon aria-hidden="true" className={cn("size-3.5 shrink-0", !sorted && "opacity-50")} />;
}

export function ApplicationsTable({
  rows,
  sort,
  onSortChange,
  pageIndex,
  pageSize,
  onPageIndexChange,
  onPageSizeChange,
}: ApplicationsTableProps) {
  const pageSizeId = useId();
  const total = rows.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePageIndex = Math.min(Math.max(0, pageIndex), pageCount - 1);

  const sorting = useMemo(() => [{ id: sort.id, desc: sort.desc }], [sort.id, sort.desc]);
  const pagination = useMemo(
    () => ({ pageIndex: safePageIndex, pageSize }),
    [safePageIndex, pageSize]
  );

  const table = useTable({
    features,
    columns,
    data: rows,
    state: { sorting, pagination },
    enableSortingRemoval: false,
    enableMultiSort: false,
    autoResetSorting: false,
    autoResetPageIndex: false,
    onSortingChange: (updater) => {
      const next = resolveUpdater(updater, sorting)[0];
      if (next) onSortChange({ id: next.id as SortId, desc: next.desc });
    },
    onPaginationChange: (updater) => {
      onPageIndexChange(resolveUpdater(updater, pagination).pageIndex);
    },
  });

  const start = total === 0 ? 0 : safePageIndex * pageSize + 1;
  const end = Math.min(total, (safePageIndex + 1) * pageSize);
  const rangeLabel =
    total === 0
      ? "No applications"
      : `${formatNumber(start)}–${formatNumber(end)} of ${formatNumber(total)}`;

  return (
    <div className="space-y-0 rounded-xl border bg-card">
      <Table>
        <caption className="sr-only">
          Applications sorted by {SORT_LABELS[sort.id].toLowerCase()}, {sort.desc ? "descending" : "ascending"}
        </caption>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <TableHead
                    key={header.id}
                    scope="col"
                    aria-sort={header.column.getCanSort() ? ariaSortFor(sorted) : undefined}
                    className="whitespace-nowrap"
                  >
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1 rounded-sm font-medium text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <table.FlexRender header={header} />
                        <SortIndicator sorted={sorted} />
                      </button>
                    ) : (
                      <table.FlexRender header={header} />
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getAllCells().map((cell) => (
                <TableCell key={cell.id} className="align-middle">
                  <table.FlexRender cell={cell} />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <nav
        aria-label="Applications pages"
        className="flex flex-wrap items-center justify-between gap-3 border-t px-3 py-2 text-sm"
      >
        <p aria-live="polite" className="tabular-nums text-muted-foreground">
          {rangeLabel}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={pageSizeId} className="text-muted-foreground">
            Rows per page
          </label>
          <select
            id={pageSizeId}
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value) as PageSize)}
            className="h-8 rounded-md border bg-background px-2 text-sm"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="max-sm:min-h-11"
            disabled={safePageIndex === 0}
            onClick={() => onPageIndexChange(safePageIndex - 1)}
          >
            Previous
          </Button>
          <span className="tabular-nums text-muted-foreground">
            Page {formatNumber(safePageIndex + 1)} of {formatNumber(pageCount)}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="max-sm:min-h-11"
            disabled={safePageIndex >= pageCount - 1}
            onClick={() => onPageIndexChange(safePageIndex + 1)}
          >
            Next
          </Button>
        </div>
      </nav>
    </div>
  );
}
