"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/crm/page-header";
import { ErrorBoundary } from "@/components/crm/error-boundary";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchInsightsBundle } from "@/lib/analytics";
import { useDateRange } from "@/lib/date-range-context";
import { isDemoMode } from "@/lib/demo";
import { qk } from "@/lib/query-keys";

const scoreChartConfig = {
  evaluations: { label: "Evaluations", color: "var(--chart-1)" },
  offers: { label: "Offers", color: "var(--chart-2)" },
} satisfies ChartConfig;

const outcomeChartConfig = {
  count: { label: "Applications", color: "var(--chart-3)" },
} satisfies ChartConfig;

export function InsightsPage() {
  const { value: dateRange } = useDateRange();
  const { data, isLoading, error } = useQuery({
    queryKey: qk.insights(dateRange),
    queryFn: () => fetchInsightsBundle(dateRange.range),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-80 rounded-lg" />
          <Skeleton className="h-80 rounded-lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-destructive">
        {error instanceof Error ? error.message : "Failed to load insights"}
      </p>
    );
  }

  if (!data) return null;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Insights"
        description={
          isDemoMode()
            ? "Demo analytics for score, outcomes, and compensation."
            : "Score distribution, outcomes, compensation, and interview results."
        }
      />

      <ErrorBoundary title="Insights failed to render">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Score distribution</CardTitle>
              <CardDescription>Evaluations by score bucket</CardDescription>
            </CardHeader>
            <CardContent>
              <ChartContainer config={scoreChartConfig} className="h-72 w-full">
                <BarChart data={data.scoreOutcomes}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" />
                  <YAxis allowDecimals={false} width={32} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="evaluations" fill="var(--color-evaluations)" radius={4} />
                  <Bar dataKey="offers" fill="var(--color-offers)" radius={4} />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Application outcomes</CardTitle>
              <CardDescription>Resolved applications in selected range</CardDescription>
            </CardHeader>
            <CardContent>
              {data.outcomeBreakdown.length === 0 ? (
                <p className="text-sm text-muted-foreground">No outcomes in range</p>
              ) : (
                <ChartContainer config={outcomeChartConfig} className="h-72 w-full">
                  <BarChart data={data.outcomeBreakdown}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} width={32} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="count" fill="var(--color-count)" radius={4} />
                  </BarChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Decline reasons</CardTitle>
              <CardDescription>Why applications were closed</CardDescription>
            </CardHeader>
            <CardContent>
              {data.declineReasons.length === 0 ? (
                <p className="text-sm text-muted-foreground">No decline reasons recorded</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {data.declineReasons.map((row) => (
                    <li
                      key={row.reason}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <span>{row.reason}</span>
                      <span className="text-muted-foreground">{row.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Compensation by seniority</CardTitle>
              <CardDescription>
                Average min/max per currency from opportunities in range
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.compensationBySeniority.length === 0 ? (
                <p className="text-sm text-muted-foreground">No compensation data</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Seniority</TableHead>
                      <TableHead>Currency</TableHead>
                      <TableHead>Avg min</TableHead>
                      <TableHead>Avg max</TableHead>
                      <TableHead>Roles</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.compensationBySeniority.map((row) => (
                      <TableRow key={`${row.currency}-${row.seniority}`}>
                        <TableCell className="capitalize">{row.seniority}</TableCell>
                        <TableCell>{row.currency}</TableCell>
                        <TableCell>{row.avgMin?.toLocaleString() ?? "—"}</TableCell>
                        <TableCell>{row.avgMax?.toLocaleString() ?? "—"}</TableCell>
                        <TableCell>{row.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Interview outcomes</CardTitle>
              <CardDescription>Results by stage in selected range</CardDescription>
            </CardHeader>
            <CardContent>
              {data.interviewOutcomes.length === 0 ? (
                <p className="text-sm text-muted-foreground">No interviews in range</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Stage</TableHead>
                      <TableHead>Result</TableHead>
                      <TableHead>Count</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.interviewOutcomes.map((row) => (
                      <TableRow key={`${row.stage}-${row.result}`}>
                        <TableCell className="capitalize">{row.stage}</TableCell>
                        <TableCell className="capitalize">{row.result}</TableCell>
                        <TableCell>{row.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </ErrorBoundary>
    </div>
  );
}
