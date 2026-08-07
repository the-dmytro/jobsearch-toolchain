"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import Link from "next/link";
import { useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApplicationWithJoins } from "./use-applications-query";

export function ApplicationsTable({ data }: { data: ApplicationWithJoins[] }) {
  const columns = useMemo<ColumnDef<ApplicationWithJoins>[]>(
    () => [
      {
        id: "title",
        header: "Role",
        accessorFn: (row) => row.opportunities?.title,
        cell: ({ row }) => (
          <Link
            href={`/applications/${row.original.id}`}
            className="font-medium hover:underline"
          >
            {row.original.opportunities?.title ?? "—"}
          </Link>
        ),
      },
      {
        id: "company",
        header: "Company",
        cell: ({ row }) => row.original.organizations?.name ?? "—",
      },
      {
        accessorKey: "status",
        header: "Status",
      },
      {
        accessorKey: "current_stage",
        header: "Stage",
      },
      {
        accessorKey: "applied_at",
        header: "Applied",
      },
    ],
    []
  );

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id}>
                  {h.isPlaceholder
                    ? null
                    : flexRender(h.column.columnDef.header, h.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length ? (
            table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
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
