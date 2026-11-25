"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { ErrorBoundary } from "@/components/crm/error-boundary";
import { PageHeader } from "@/components/crm/page-header";
import { DashboardCard, type CardStatus } from "@/components/dashboard/dashboard-card";
import { rangePhrase, stageLabel } from "@/components/dashboard/labels";
import { TextAlternative } from "@/components/dashboard/text-alternative";
import { Badge } from "@/components/ui/badge";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { CompensationRow, InsightsBundle, ScoreOutcomeRow } from "@/lib/analytics";
import { useInsightsBundle } from "@/lib/analytics-query";
import { useDateRange } from "@/lib/date-range-context";
import { isDemoMode } from "@/lib/demo";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";

/** Rows shown in the decline reasons list before the rest are grouped as "Other". */
const DECLINE_ROW_LIMIT = 8;

const BAND_LABELS: Readonly<Record<string, string>> = {
  "0-2": "0 to 2",
  "3-4": "3 to 4",
  "5-6": "5 to 6",
  "7-8": "7 to 8",
  "9-10": "9 to 10",
  unknown: "No score",
};

const scoreChartConfig = {
  evaluations: { label: "Evaluations", color: "var(--chart-1)" },
} satisfies ChartConfig;

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/* ------------------------------------------------------------------ */
/* Match score                                                         */
/* ------------------------------------------------------------------ */

export function MatchScoreCard({ rows, rangeText, status }: { rows?: ScoreOutcomeRow[]; rangeText: string; status: CardStatus }) {
  const data = (rows ?? []).map((row) => ({
    band: BAND_LABELS[row.bucket] ?? row.bucket,
    evaluations: row.evaluations,
  }));

  return (
    <DashboardCard
      title="Match score"
      description={`Evaluations by match score, 0 to 10. ${rangeText}. Each evaluation counts once.`}
      status={status}
      isEmpty={rows !== undefined && rows.length === 0}
      emptyTitle="No evaluations in this range"
      emptyDescription="Scores appear here once opportunities in the range have been evaluated."
    >
      <div aria-hidden="true">
        <ChartContainer config={scoreChartConfig} className="h-64 w-full">
          <BarChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="band" tick={{ fontSize: 11 }} tickLine={false} />
            <YAxis allowDecimals={false} width={32} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="evaluations" fill="var(--color-evaluations)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </div>
      <TextAlternative<ScoreOutcomeRow>
        caption={`Match score distribution. ${rangeText}.`}
        columns={[
          { key: "band", header: "Match score", cell: (row) => BAND_LABELS[row.bucket] ?? row.bucket },
          { key: "evaluations", header: "Evaluations", cell: (row) => formatNumber(row.evaluations) },
          { key: "withApplication", header: "With application", cell: (row) => formatNumber(row.withApplication) },
          { key: "offers", header: "Offers", cell: (row) => formatNumber(row.offers) },
          { key: "rate", header: "Offer rate", cell: (row) => (row.offerRate.value == null ? "Not enough data" : `${formatPercent(row.offerRate.value)} of ${formatNumber(row.offerRate.n)}`) },
        ]}
        rows={rows ?? []}
      />
    </DashboardCard>
  );
}

/* ------------------------------------------------------------------ */
/* Outcomes and decline reasons (horizontal bars)                      */
/* ------------------------------------------------------------------ */

type BarRow = { key: string; label: string; count: number };

function BarList({ rows, total, unit }: { rows: BarRow[]; total: number; unit: string }) {
  const max = Math.max(1, ...rows.map((row) => row.count));
  return (
    <ul className="space-y-3" aria-label={unit}>
      {rows.map((row) => (
        <li key={row.key} className="space-y-1">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate font-medium">{row.label}</span>
            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
              {formatNumber(row.count)}
              {total > 0 ? ` · ${formatPercent(row.count / total)}` : ""}
            </span>
          </div>
          <div aria-hidden="true" className="h-2 overflow-hidden rounded-sm bg-muted">
            <div className="h-full rounded-sm bg-chart-1" style={{ width: `${(row.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function OutcomesCard({ data, rangeText, status }: { data?: InsightsBundle; rangeText: string; status: CardStatus }) {
  const rows = (data?.outcomeBreakdown ?? []).map((row) => ({ key: row.outcome, label: row.label, count: row.count }));
  const total = rows.reduce((sum, row) => sum + row.count, 0);

  return (
    <DashboardCard
      title="Outcomes"
      description={`Applications applied in range, by outcome. ${rangeText}.`}
      status={status}
      isEmpty={data !== undefined && rows.length === 0}
      emptyTitle="No applications in this range"
      emptyDescription="Outcomes appear here for applications applied in the selected range."
    >
      <BarList rows={rows} total={total} unit="Application outcomes" />
    </DashboardCard>
  );
}

export function DeclineReasonsCard({ data, rangeText, status }: { data?: InsightsBundle; rangeText: string; status: CardStatus }) {
  const top = (data?.declineReasons ?? []).slice(0, DECLINE_ROW_LIMIT);
  const other = data?.declineOther ?? 0;
  const rows: BarRow[] = top.map((row) => ({ key: row.reason, label: row.reason, count: row.count }));
  if (other > 0) rows.push({ key: "other", label: "Other", count: other });
  const total = rows.reduce((sum, row) => sum + row.count, 0);

  return (
    <DashboardCard
      title="Decline reasons"
      description={`Why applications were declined, most common first. ${rangeText}. Top ${DECLINE_ROW_LIMIT} reasons, the rest grouped as Other.`}
      status={status}
      isEmpty={data !== undefined && rows.length === 0}
      emptyTitle="No decline reasons recorded"
      emptyDescription="Reasons appear here when a declined application has one recorded."
    >
      <BarList rows={rows} total={total} unit="Decline reasons" />
    </DashboardCard>
  );
}

/* ------------------------------------------------------------------ */
/* Compensation, one table per currency                                */
/* ------------------------------------------------------------------ */

function amount(value: number | null, currency: string): string {
  if (value == null) return "—";
  return currency === "unknown" ? formatNumber(value) : formatCurrency(value, currency);
}

function groupByCurrency(rows: CompensationRow[]): Array<{ currency: string; rows: CompensationRow[] }> {
  const groups = new Map<string, CompensationRow[]>();
  for (const row of rows) {
    const list = groups.get(row.currency) ?? [];
    list.push(row);
    groups.set(row.currency, list);
  }
  return Array.from(groups.entries())
    .map(([currency, list]) => ({ currency, rows: list }))
    .sort((a, b) => b.rows.reduce((s, r) => s + r.count, 0) - a.rows.reduce((s, r) => s + r.count, 0));
}

export function CompensationCard({ data, rangeText, status }: { data?: InsightsBundle; rangeText: string; status: CardStatus }) {
  const groups = groupByCurrency(data?.compensationBySeniority ?? []);

  return (
    <DashboardCard
      title="Compensation by seniority"
      description={`Average advertised minimum and maximum, per currency. ${rangeText}. Currencies are never mixed.`}
      status={status}
      isEmpty={data !== undefined && groups.length === 0}
      emptyTitle="No compensation data in this range"
      emptyDescription="Averages appear here once opportunities with a salary range are in the selected range."
    >
      {groups.map((group) => (
        <section key={group.currency} aria-labelledby={`comp-${group.currency}`} className="space-y-2">
          <h3 id={`comp-${group.currency}`} className="text-sm font-medium">
            {group.currency === "unknown" ? "Currency not set" : group.currency}
          </h3>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Seniority</TableHead>
                  <TableHead className="text-right">Average min</TableHead>
                  <TableHead className="text-right">Average max</TableHead>
                  <TableHead className="text-right">Roles</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {group.rows.map((row) => (
                  <TableRow key={`${group.currency}-${row.seniority}`}>
                    <TableCell>{row.seniority === "unspecified" ? "Not specified" : capitalize(row.seniority)}</TableCell>
                    <TableCell className="text-right tabular-nums">{amount(row.avgMin, group.currency)}</TableCell>
                    <TableCell className="text-right tabular-nums">{amount(row.avgMax, group.currency)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(row.count)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}
    </DashboardCard>
  );
}

/* ------------------------------------------------------------------ */
/* Interview outcomes                                                  */
/* ------------------------------------------------------------------ */

function InterviewOutcomesCard({ data, rangeText, status }: { data?: InsightsBundle; rangeText: string; status: CardStatus }) {
  const rows = data?.interviewOutcomes ?? [];

  return (
    <DashboardCard
      title="Interview outcomes"
      description={`Interviews by stage and result. ${rangeText}, by scheduled date.`}
      status={status}
      isEmpty={data !== undefined && rows.length === 0}
      emptyTitle="No interviews in this range"
      emptyDescription="Interviews scheduled in the selected range appear here with their result."
    >
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Stage</TableHead>
              <TableHead>Result</TableHead>
              <TableHead className="text-right">Interviews</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={`${row.stage}-${row.result}`}>
                <TableCell>{stageLabel(row.stage)}</TableCell>
                <TableCell>{capitalize(row.result)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatNumber(row.count)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </DashboardCard>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export function InsightsPage() {
  const { value: dateRange } = useDateRange();
  const query = useInsightsBundle(dateRange);
  const data = query.data;
  const rangeText = rangePhrase(dateRange);

  const status: CardStatus = {
    loading: query.isPending,
    error: query.isError ? query.error : undefined,
    onRetry: () => void query.refetch(),
  };

  return (
    <div className="flex min-w-0 flex-col gap-8">
      <PageHeader
        title="Insights"
        description={`Match score, outcomes, decline reasons, compensation and interviews ${rangePhrase(dateRange)}.`}
        actions={isDemoMode() ? <Badge variant="outline">Demo data</Badge> : undefined}
      />

      <ErrorBoundary title="Insights failed to render">
        <div className="grid min-w-0 gap-4 lg:grid-cols-2">
          <MatchScoreCard rows={data?.scoreOutcomes} rangeText={rangeText} status={status} />
          <OutcomesCard data={data} rangeText={rangeText} status={status} />
          <DeclineReasonsCard data={data} rangeText={rangeText} status={status} />
          <CompensationCard data={data} rangeText={rangeText} status={status} />
          <div className="lg:col-span-2">
            <InterviewOutcomesCard data={data} rangeText={rangeText} status={status} />
          </div>
        </div>
      </ErrorBoundary>
    </div>
  );
}
