"use client";

import { useQuery } from "@tanstack/react-query";
import { ArtifactOpenButton } from "@/components/crm/artifact-open-button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { createClient } from "@/lib/supabase/client";
import type { Tables } from "@/types/database.types";

export function TranscriptsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["transcripts", "artifacts"],
    queryFn: async () => {
      const supabase = createClient();
      const { data: arts, error: e1 } = await supabase
        .from("artifacts")
        .select("*")
        .order("created_at", { ascending: false })
        .limit(400);
      if (e1) throw e1;
      const list = (arts ?? []) as Tables<"artifacts">[];
      return list
        .filter(
          (a) =>
            String(a.artifact_type ?? "")
              .toLowerCase()
              .includes("transcript") ||
            String(a.title ?? "")
              .toLowerCase()
              .includes("transcript")
        )
        .slice(0, 100);
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) {
    return (
      <p className="text-destructive">
        {error instanceof Error ? error.message : "Error"}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Transcripts</h1>
        <p className="text-sm text-muted-foreground">
          Artifacts matching transcript (type/title). Open via signed URL (requires service role on
          server).
        </p>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-28"> </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground">
                  No transcript artifacts found
                </TableCell>
              </TableRow>
            ) : (
              (data ?? []).map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.title ?? a.artifact_type}</TableCell>
                  <TableCell>{a.artifact_type}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {a.created_at.slice(0, 10)}
                  </TableCell>
                  <TableCell>
                    <ArtifactOpenButton artifact={a} />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Full-text chunks</CardTitle>
          <CardDescription>
            Open an application with a linked interview transcript to search chunks in context.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Use Applications → Transcripts tab when `document_chunks` exist for the artifact.
        </CardContent>
      </Card>
    </div>
  );
}
