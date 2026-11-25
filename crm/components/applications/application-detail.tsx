"use client";

import { mutationMessage, unwrapAction } from "@/components/applications/action-error";
import { ErrorState } from "@/components/crm/error-state";
import { PageHeader } from "@/components/crm/page-header";
import { SafeExternalLink } from "@/components/crm/safe-external-link";
import { TableSkeleton } from "@/components/crm/table-skeleton";
import { formatDate, formatNumber } from "@/lib/format";
import { normalizeScore } from "@/lib/score";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { ArtifactOpenButton } from "@/components/crm/artifact-open-button";
import { ApplicationEditSheet } from "@/components/applications/application-edit-sheet";
import {
  BOARD_COLUMN_LABELS,
  OUTCOME_LABELS,
  type BoardColumn,
} from "@/components/applications/application-model";
import {
  useApplicationDetail,
  type ApplicationDetailBundle,
} from "@/components/applications/use-application-detail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { createCommunication } from "@/lib/actions/communications";
import { createContact } from "@/lib/actions/contacts";
import { createInterview } from "@/lib/actions/interviews";
import { communicationInsertSchema } from "@/lib/schemas/communication";
import { contactInsertSchema } from "@/lib/schemas/contact";
import { interviewInsertSchema } from "@/lib/schemas/interview";
import { invalidateAfterMutation } from "@/lib/mutations";
import {
  isStageChangeEvent,
  normalizeStage,
  stageFromEvent,
  stageIndex,
  stageProgress,
} from "@/lib/stages";
import { z } from "zod";

function Timeline({ bundle }: { bundle: ApplicationDetailBundle }) {
  const combined = useMemo(() => {
    const rows: { at: string; label: string; sub?: string }[] = [];
    for (const e of bundle.events) {
      rows.push({
        at: e.event_at ?? e.created_at,
        label: e.title ?? e.event_type,
        sub: e.description ?? undefined,
      });
    }
    for (const c of bundle.communications) {
      rows.push({
        at: c.sent_at ?? c.updated_at,
        label: c.subject ?? "Communication",
        sub: c.summary ?? undefined,
      });
    }
    for (const i of bundle.interviews) {
      rows.push({
        at: i.scheduled_at ?? i.created_at,
        label: `Interview${i.stage ? `: ${i.stage}` : ""}`,
        sub: i.meeting_url ?? undefined,
      });
    }
    for (const ev of bundle.evaluations) {
      rows.push({
        at: ev.evaluated_at,
        label: `Evaluation${normalizeScore(ev.score) !== null ? ` (${formatNumber(normalizeScore(ev.score))})` : ""}`,
        sub: ev.main_match ?? undefined,
      });
    }
    rows.sort(
      (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime()
    );
    return rows;
  }, [bundle]);

  return (
    <div className="space-y-3">
      {combined.length === 0 ? (
        <p className="text-sm text-muted-foreground">No timeline entries yet.</p>
      ) : (
        combined.map((r, i) => (
          <div key={`${r.at}-${i}`} className="border-l-2 pl-3">
            <p className="text-xs text-muted-foreground">
              {formatDate(r.at, { withTime: true })}
            </p>
            <p className="text-sm font-medium">{r.label}</p>
            {r.sub ? (
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{r.sub}</p>
            ) : null}
          </div>
        ))
      )}
    </div>
  );
}

export function ApplicationDetail({ id }: { id: string }) {
  const { data, isLoading, error, refetch } = useApplicationDetail(id);
  const [editOpen, setEditOpen] = useState(false);
  const [transcriptFilter, setTranscriptFilter] = useState("");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Application" description="Loading application details." />
        <TableSkeleton rows={4} cols={3} label="Loading application" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <PageHeader title="Application" />
        <ErrorState
          title="This application couldn't load"
          error={error}
          onRetry={() => void refetch()}
        />
        <Link href="/applications" className="text-sm text-primary underline-offset-4 hover:underline">
          Back to applications
        </Link>
      </div>
    );
  }

  const app = data.application;
  const title = app.opportunities?.title ?? "Application";
  const company = app.organizations?.name ?? "—";
  const history = data.events
    .filter((e) => isStageChangeEvent(e.event_type))
    .map((e) => stageFromEvent(e));
  const progress = stageProgress(app.current_stage, history);
  const furthest = furthestStage(app.current_stage, history);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{title}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {app.organization_id ? (
              <Link href={`/companies/${app.organization_id}`} className="hover:underline">
                {company}
              </Link>
            ) : (
              <span>{company}</span>
            )}
            {app.providers?.name ? (
              <Badge variant="outline">{app.providers.name}</Badge>
            ) : null}
          </div>
        </div>
        <Button type="button" onClick={() => setEditOpen(true)}>
          Edit application
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Stage progress</CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            <span>Furthest stage: {BOARD_COLUMN_LABELS[furthest]}</span>
            {progress.terminal ? (
              <Badge variant="outline">{OUTCOME_LABELS[progress.terminal]}</Badge>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Progress value={progress.percent} />
        </CardContent>
      </Card>

      <Tabs defaultValue="overview">
        <TabsList className="flex flex-wrap h-auto gap-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="communications">Communications</TabsTrigger>
          <TabsTrigger value="interviews">Interviews</TabsTrigger>
          <TabsTrigger value="transcripts">Transcripts</TabsTrigger>
          <TabsTrigger value="contacts">Contacts</TabsTrigger>
          <TabsTrigger value="source">Source & evaluation</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Summary label="Status" value={app.status} />
            <Summary label="Stage" value={app.current_stage ?? "—"} />
            <Summary label="Applied" value={formatDate(app.applied_at)} />
            <Summary label="Outcome" value={app.outcome ?? "—"} />
            <Summary label="Salary" value={app.salary_requested_text ?? "—"} />
          </div>
          {app.notes ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Notes</CardTitle>
              </CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm">{app.notes}</CardContent>
            </Card>
          ) : null}
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <Timeline bundle={data} />
        </TabsContent>

        <TabsContent value="communications" className="mt-4 space-y-6">
          <CommunicationQuickForm applicationId={app.id} organizationId={app.organization_id} />
          <Separator />
          <div className="space-y-3">
            {data.communications.length === 0 ? (
              <p className="text-sm text-muted-foreground">No communications logged</p>
            ) : (
              data.communications.map((c) => (
                <Card key={c.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{c.subject ?? "Message"}</CardTitle>
                    <CardDescription>
                      {formatDate(c.sent_at, { withTime: true })}{" "}
                      · {c.channel ?? "—"} · {c.direction ?? "—"}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="text-sm whitespace-pre-wrap">
                    {c.summary ?? "—"}
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>

        <TabsContent value="interviews" className="mt-4 space-y-6">
          <InterviewQuickForm applicationId={app.id} organizationId={app.organization_id} />
          <div className="space-y-3">
            {data.interviews.length === 0 ? (
              <p className="text-sm text-muted-foreground">No interviews</p>
            ) : (
              data.interviews.map((i) => (
                <Card key={i.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      {i.stage ?? "Interview"}{" "}
                      <Link href={`/interviews/${i.id}`} className="text-primary text-sm font-normal">
                        Open
                      </Link>
                    </CardTitle>
                    <CardDescription>
                      {formatDate(i.scheduled_at, { withTime: true })}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="text-sm">{i.notes ?? "—"}</CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>

        <TabsContent value="transcripts" className="mt-4 space-y-4">
          <Input
            aria-label="Filter transcript text"
            placeholder="Filter transcript text…"
            value={transcriptFilter}
            onChange={(e) => setTranscriptFilter(e.target.value)}
          />
          {data.interviews.filter((i) => i.transcript_artifact_id).length === 0 ? (
            <p className="text-sm text-muted-foreground">No transcripts linked yet.</p>
          ) : (
            data.interviews
              .filter((i) => i.transcript_artifact_id)
              .map((i) => (
                <Card key={i.id}>
                  <CardHeader>
                    <CardTitle className="text-base">
                      Transcript · {i.stage ?? i.id.slice(0, 8)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScrollArea className="h-60 rounded-md border p-3">
                      <TranscriptChunks
                        chunks={
                          data.chunksByArtifactId[i.transcript_artifact_id!] ?? []
                        }
                        filter={transcriptFilter}
                      />
                    </ScrollArea>
                  </CardContent>
                </Card>
              ))
          )}
        </TabsContent>

        <TabsContent value="contacts" className="mt-4 space-y-6">
          <ContactQuickForm
            applicationId={app.id}
            organizationId={app.organization_id}
          />
          <div className="space-y-2">
            {data.contacts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No contacts for this org</p>
            ) : (
              data.contacts.map((c) => (
                <Card key={c.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">
                      <Link href={`/contacts/${c.id}`} className="hover:underline">
                        {c.full_name ?? "Contact"}
                      </Link>
                    </CardTitle>
                    <CardDescription>{c.role_title ?? c.email ?? "—"}</CardDescription>
                  </CardHeader>
                </Card>
              ))
            )}
          </div>
        </TabsContent>

        <TabsContent value="source" className="mt-4 space-y-4">
          {app.opportunities ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Opportunity</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p>{app.opportunities.title}</p>
                {app.opportunities.source_url ? (
                  <SafeExternalLink
                    href={app.opportunities.source_url}
                    className="text-primary underline"
                  >
                    Source URL
                  </SafeExternalLink>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Evaluations</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.evaluations.length === 0 ? (
                <p className="text-sm text-muted-foreground">None</p>
              ) : (
                data.evaluations.map((ev) => (
                  <div key={ev.id} className="rounded-md border p-3 text-sm">
                    <p className="font-medium">
                      Score {normalizeScore(ev.score) === null ? "—" : formatNumber(normalizeScore(ev.score))} ·{" "}
                      {ev.recommendation ?? ev.verdict ?? "—"}
                    </p>
                    <p className="text-muted-foreground">{ev.main_match}</p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Source items</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.sourceItems.length === 0 ? (
                <p className="text-sm text-muted-foreground">None</p>
              ) : (
                data.sourceItems.map((s) => (
                  <div key={s.id} className="text-sm border-b pb-2">
                    <p className="font-medium">{s.title ?? s.source_type}</p>
                    {s.source_url ? (
                      <SafeExternalLink href={s.source_url} className="text-primary underline">
                        Link
                      </SafeExternalLink>
                    ) : null}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="files" className="mt-4 space-y-3">
          {data.artifacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No files attached yet.</p>
          ) : (
            data.artifacts.map((a) => (
              <Card key={a.id}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <div>
                    <CardTitle className="text-base">{a.title ?? a.artifact_type}</CardTitle>
                    <CardDescription>{a.mime_type ?? "—"}</CardDescription>
                  </div>
                  <ArtifactOpenButton artifact={a} />
                </CardHeader>
              </Card>
            ))
          )}
        </TabsContent>
      </Tabs>

      <ApplicationEditSheet
        application={app}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
    </div>
  );
}

/**
 * The furthest pipeline stage the application reached, from its current stage and
 * its stage history. Declined or withdrawn applications keep the step they reached.
 */
function furthestStage(current: string | null, history: (string | null)[]): BoardColumn {
  let best: BoardColumn = "applied";
  let bestIndex = 0;
  for (const raw of [current, ...history]) {
    const index = stageIndex(raw);
    if (index > bestIndex) {
      bestIndex = index;
      best = normalizeStage(raw) as BoardColumn;
    }
  }
  return best;
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  );
}

function TranscriptChunks({
  chunks,
  filter,
}: {
  chunks: { chunk_index: number; content: string }[];
  filter: string;
}) {
  const q = filter.trim().toLowerCase();
  const list = q
    ? chunks.filter((c) => c.content.toLowerCase().includes(q))
    : chunks;
  if (list.length === 0) {
    return <p className="text-sm text-muted-foreground">No chunks match</p>;
  }
  return (
    <div className="space-y-3">
      {list.map((c) => (
        <p key={c.chunk_index} className="text-sm whitespace-pre-wrap">
          {c.content}
        </p>
      ))}
    </div>
  );
}

function CommunicationQuickForm({
  applicationId,
  organizationId,
}: {
  applicationId: string;
  organizationId: string | null;
}) {
  const qc = useQueryClient();
  const schema = communicationInsertSchema;
  type FormValues = z.infer<typeof schema>;
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      application_id: applicationId,
      organization_id: organizationId,
      channel: "email",
      direction: "inbound",
      subject: "",
      summary: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async (v: FormValues) => {
      const res = await createCommunication(v);
      unwrapAction(res);
    },
    onSuccess: () => {
      toast.success("Logged");
      void invalidateAfterMutation(qc, { applicationId });
      form.reset({ ...form.getValues(), subject: "", summary: "" });
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Log communication</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
            className="grid gap-3 sm:grid-cols-2"
          >
            <FormField
              control={form.control}
              name="subject"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Subject</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="summary"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Summary</FormLabel>
                  <FormControl>
                    <Textarea {...field} value={field.value ?? ""} rows={3} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={mutation.isPending}>
              Save
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

function InterviewQuickForm({
  applicationId,
  organizationId,
}: {
  applicationId: string;
  organizationId: string | null;
}) {
  const qc = useQueryClient();
  const schema = interviewInsertSchema;
  type FormValues = z.infer<typeof schema>;
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      application_id: applicationId,
      organization_id: organizationId,
      stage: "",
      scheduled_at: "",
      meeting_url: "",
      notes: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async (v: FormValues) => {
      const res = await createInterview({
        ...v,
        scheduled_at: v.scheduled_at
          ? new Date(v.scheduled_at).toISOString()
          : null,
        stage: v.stage || null,
        meeting_url: v.meeting_url || null,
        notes: v.notes || null,
      });
      unwrapAction(res);
    },
    onSuccess: () => {
      toast.success("Interview scheduled");
      void invalidateAfterMutation(qc, { applicationId });
      form.reset();
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Schedule interview</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
            className="grid gap-3 sm:grid-cols-2"
          >
            <FormField
              control={form.control}
              name="stage"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Stage</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="scheduled_at"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>When (ISO local)</FormLabel>
                  <FormControl>
                    <Input type="datetime-local" {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="meeting_url"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Meeting URL</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Notes</FormLabel>
                  <FormControl>
                    <Textarea {...field} value={field.value ?? ""} rows={2} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={mutation.isPending}>
              Create
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

function ContactQuickForm({
  applicationId,
  organizationId,
}: {
  applicationId: string;
  organizationId: string | null;
}) {
  const qc = useQueryClient();
  const schema = contactInsertSchema;
  type FormValues = z.infer<typeof schema>;
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      organization_id: organizationId,
      full_name: "",
      email: "",
      role_title: "",
      notes: "",
    },
  });

  const mutation = useMutation({
    mutationFn: async (v: FormValues) => {
      if (!organizationId) throw new Error("No organization on application");
      const res = await createContact({
        ...v,
        organization_id: organizationId,
        email: v.email === "" ? undefined : v.email,
      });
      unwrapAction(res);
    },
    onSuccess: () => {
      toast.success("Contact added");
      void invalidateAfterMutation(qc, { applicationId });
      form.reset({
        organization_id: organizationId,
        full_name: "",
        email: "",
        role_title: "",
        notes: "",
      });
    },
    onError: (e) => toast.error(mutationMessage(e)),
  });

  if (!organizationId) {
    return (
      <p className="text-sm text-muted-foreground">
        Link an organization on the opportunity to add contacts.
      </p>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Add contact</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
            className="grid gap-3 sm:grid-cols-2"
          >
            <FormField
              control={form.control}
              name="full_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="role_title"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Role</FormLabel>
                  <FormControl>
                    <Input {...field} value={field.value ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={mutation.isPending}>
              Add
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
