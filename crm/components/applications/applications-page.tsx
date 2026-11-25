"use client";

import { LayoutGridIcon, TableIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";

import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { TableSkeleton } from "@/components/crm/table-skeleton";
import { Button } from "@/components/ui/button";

import { ApplicationsKanban } from "./applications-kanban";
import { ApplicationsTable } from "./applications-table";
import { ApplicationsToolbar } from "./applications-toolbar";
import {
  buildListSearchParams,
  companyOptions,
  decorateApplications,
  filterApplications,
  parseListState,
  type ListState,
  type PageSize,
  type SortId,
} from "./application-model";
import { useApplicationsQuery } from "./use-applications-query";

const TITLE = "Applications";
const DESCRIPTION = "Every role you are tracking, its stage, and how long it has been there.";

/**
 * URL-backed list state. Filters, sort, page, page size and view all live in
 * the query string, so a link or a refresh keeps the same view.
 */
function useApplicationsListState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = useMemo(() => parseListState(searchParams), [searchParams]);

  const replaceState = useCallback(
    (next: ListState) => {
      const query = buildListSearchParams(next).toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router]
  );

  /** Filter changes start again on page 1. */
  const changeFilters = useCallback(
    (patch: Partial<ListState>) => replaceState({ ...state, ...patch, page: 1 }),
    [replaceState, state]
  );

  const clearFilters = useCallback(
    () =>
      replaceState({
        ...state,
        q: "",
        stages: [],
        outcome: null,
        company: null,
        stalled: false,
        page: 1,
      }),
    [replaceState, state]
  );

  const changeSort = useCallback(
    (sort: SortId, desc: boolean) => replaceState({ ...state, sort, desc, page: 1 }),
    [replaceState, state]
  );

  const changePage = useCallback(
    (pageIndex: number) => replaceState({ ...state, page: pageIndex + 1 }),
    [replaceState, state]
  );

  const changePageSize = useCallback(
    (pageSize: PageSize) => replaceState({ ...state, pageSize, page: 1 }),
    [replaceState, state]
  );

  const changeView = useCallback(
    (view: ListState["view"]) => replaceState({ ...state, view }),
    [replaceState, state]
  );

  return { state, changeFilters, clearFilters, changeSort, changePage, changePageSize, changeView };
}

function ViewToggle({
  view,
  onChange,
}: {
  view: ListState["view"];
  onChange: (view: ListState["view"]) => void;
}) {
  return (
    <div className="flex gap-2">
      <Button
        type="button"
        variant={view === "table" ? "default" : "outline"}
        size="sm"
        aria-pressed={view === "table"}
        onClick={() => onChange("table")}
      >
        <TableIcon aria-hidden="true" />
        Table
      </Button>
      <Button
        type="button"
        variant={view === "board" ? "default" : "outline"}
        size="sm"
        aria-pressed={view === "board"}
        onClick={() => onChange("board")}
      >
        <LayoutGridIcon aria-hidden="true" />
        Board
      </Button>
    </div>
  );
}

function ApplicationsScreen() {
  const list = useApplicationsListState();
  const query = useApplicationsQuery();
  const { state } = list;

  // Days in stage are counted from the moment this screen was opened.
  const [clockMs] = useState(() => Date.now());
  const rows = useMemo(
    () => (query.data ? decorateApplications(query.data, clockMs) : null),
    [query.data, clockMs]
  );
  const filtered = useMemo(
    () => (rows ? filterApplications(rows, state) : []),
    [rows, state]
  );
  const companies = useMemo(() => (rows ? companyOptions(rows) : []), [rows]);

  if (query.isError && !query.data) {
    return (
      <div className="space-y-6">
        <PageHeader title={TITLE} description={DESCRIPTION} />
        <ErrorState
          title="Applications couldn't load"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }

  const total = rows?.length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title={TITLE}
        description={DESCRIPTION}
        count={rows ? filtered.length : undefined}
        actions={<ViewToggle view={state.view} onChange={list.changeView} />}
      />

      <ApplicationsToolbar
        filters={state}
        companies={companies}
        matchCount={filtered.length}
        totalCount={total}
        disabled={!rows}
        onChange={list.changeFilters}
        onClear={list.clearFilters}
      />

      {!rows ? (
        <TableSkeleton rows={8} cols={6} label="Loading applications" />
      ) : total === 0 ? (
        <EmptyState
          title="No applications yet"
          description="Applications appear here once you start tracking a role."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No applications match these filters"
          description="Try a different search, or clear the filters to see everything."
          action={
            <Button type="button" variant="outline" size="sm" onClick={list.clearFilters}>
              Clear filters
            </Button>
          }
        />
      ) : state.view === "board" ? (
        <ApplicationsKanban rows={filtered} />
      ) : (
        <ApplicationsTable
          rows={filtered}
          sort={{ id: state.sort, desc: state.desc }}
          onSortChange={(sort) => list.changeSort(sort.id, sort.desc)}
          pageIndex={state.page - 1}
          pageSize={state.pageSize}
          onPageIndexChange={list.changePage}
          onPageSizeChange={list.changePageSize}
        />
      )}
    </div>
  );
}

/** Applications list. Filters and view are read from the URL inside a Suspense boundary, as Next requires. */
export function ApplicationsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <PageHeader title={TITLE} description={DESCRIPTION} />
          <TableSkeleton rows={8} cols={6} label="Loading applications" />
        </div>
      }
    >
      <ApplicationsScreen />
    </Suspense>
  );
}
