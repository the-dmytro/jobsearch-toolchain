"use client";

import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApplicationWithJoins } from "./use-applications-query";

// Core row model only: no sorting, filtering or pagination features are enabled.
const features = tableFeatures({});
const columnHelper = createColumnHelper<typeof features, ApplicationWithJoins>();

const columns = columnHelper.columns([
  columnHelper.accessor((row) => row.opportunities?.title, {
    id: "title",
    header: "Role",
    cell: ({ row }) => (
      <Link
        href={`/applications/${row.original.id}`}
        className="font-medium hover:underline"
      >
        {row.original.opportunities?.title ?? "—"}
      </Link>
    ),
  }),
  columnHelper.display({
    id: "company",
    header: "Company",
    cell: ({ row }) => row.original.organizations?.name ?? "—",
  }),
  columnHelper.accessor("status", { header: "Status" }),
  columnHelper.accessor("current_stage", { header: "Stage" }),
  columnHelper.accessor("applied_at", { header: "Applied" }),
]);

export function ApplicationsTable({ data }: { data: ApplicationWithJoins[] }) {
  const table = useTable({ features, columns, data });

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id}>
                  {h.isPlaceholder ? null : <table.FlexRender header={h} />}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length ? (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getAllCells().map((cell) => (
                  <TableCell key={cell.id}>
                    <table.FlexRender cell={cell} />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center">
                No applications
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
