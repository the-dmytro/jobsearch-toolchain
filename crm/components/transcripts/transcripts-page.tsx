"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ArtifactOpenButton } from "@/components/crm/artifact-open-button";
import { EmptyState } from "@/components/crm/empty-state";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { TableSkeleton } from "@/components/crm/table-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetchAll } from "@/lib/fetch-all";
import { formatDate, formatRelative } from "@/lib/format";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

const TYPE_LABELS: Record<string, string> = {
  transcript: "Interview transcript",
  report: "Report",
  evaluation: "Evaluation",
  cv: "CV",
  cover_letter: "Cover letter",
  job_description: "Job description",
};

/** A readable name for a stored file type. Unknown types are tidied, not hidden. */
export function artifactTypeLabel(type: string | null | undefined): string {
  const key = (type ?? "").trim().toLowerCase();
  if (!key) return "File";
  if (TYPE_LABELS[key]) return TYPE_LABELS[key];
  const words = key.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Transcripts are files whose type or title says so. */
export function isTranscript(artifact: Pick<Tables<"artifacts">, "artifact_type" | "title">): boolean {
  return (
    artifact.artifact_type.toLowerCase().includes("transcript") ||
    (artifact.title ?? "").toLowerCase().includes("transcript")
  );
}

export function TranscriptsPage() {
  const query = useQuery({
    queryKey: ["transcripts", "artifacts"],
    queryFn: async () => {
      const supabase = createClient();
      const artifacts = await fetchAll<Tables<"artifacts">>((from, to) =>
        supabase.from("artifacts").select("*").order("id").range(from, to)
      );
      return artifacts
        .filter(isTranscript)
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    },
  });
  const [search, setSearch] = useState("");

  const data = query.data;
  const filtered = useMemo(() => {
    const rows = data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      [row.title ?? "", row.artifact_type].some((text) => text.toLowerCase().includes(q))
    );
  }, [data, search]);

  const header = (
    <PageHeader
      title="Transcripts"
      description="Interview transcripts stored as files. Open one to read it."
      count={data ? filtered.length : undefined}
    />
  );

  if (query.isError && !data) {
    return (
      <div className="space-y-6">
        {header}
        <ErrorState title="Transcripts couldn't load" error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {!data ? (
        <TableSkeleton rows={6} cols={4} label="Loading transcripts" />
      ) : data.length === 0 ? (
        <EmptyState
          title="No transcripts yet"
          description="Transcripts appear here after an interview recording has been saved."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="transcript-search" className="sr-only">
              Search transcripts
            </label>
            <Input
              id="transcript-search"
              type="search"
              value={search}
              placeholder="Title or file type"
              onChange={(event) => setSearch(event.target.value)}
              className="max-w-md"
            />
            {search ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setSearch("")}>
                Clear search
              </Button>
            ) : null}
          </div>

          {filtered.length === 0 ? (
            <EmptyState title="No transcripts match this search" description="Try a different title." />
          ) : (
            <div className="rounded-xl border bg-card">
              <Table>
                <caption className="sr-only">Transcripts, newest first</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Title</TableHead>
                    <TableHead scope="col">Type</TableHead>
                    <TableHead scope="col">Added</TableHead>
                    <TableHead scope="col">
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((artifact) => (
                    <TableRow key={artifact.id}>
                      <TableCell className="font-medium">{artifact.title ?? "Untitled transcript"}</TableCell>
                      <TableCell>{artifactTypeLabel(artifact.artifact_type)}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        <time dateTime={artifact.created_at} title={formatRelative(artifact.created_at)}>
                          {formatDate(artifact.created_at)}
                        </time>
                      </TableCell>
                      <TableCell>
                        <ArtifactOpenButton artifact={artifact} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
