import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompensationCard, DeclineReasonsCard, MatchScoreCard } from "@/components/insights/insights-page";
import type { CompensationRow, InsightsBundle, ScoreOutcomeRow } from "@/lib/analytics";
import { formatCurrency } from "@/lib/format";

const READY = { loading: false } as const;

const COMPENSATION: CompensationRow[] = [
  { currency: "USD", seniority: "senior", avgMin: 110000, avgMax: 140000, count: 2 },
  { currency: "EUR", seniority: "senior", avgMin: 90000, avgMax: 120000, count: 1 },
  { currency: "USD", seniority: "junior", avgMin: 60000, avgMax: null, count: 1 },
  { currency: "unknown", seniority: "unspecified", avgMin: 50, avgMax: 60, count: 1 },
];

describe("CompensationCard", () => {
  it("splits the table by currency, so no table mixes currencies", () => {
    render(<CompensationCard data={bundle({ compensationBySeniority: COMPENSATION })} rangeText="in the last 30 days" status={READY} />);

    const usd = screen.getByRole("heading", { name: "USD" }).closest("section");
    const eur = screen.getByRole("heading", { name: "EUR" }).closest("section");
    const unknown = screen.getByRole("heading", { name: "Currency not set" }).closest("section");
    expect(usd).not.toBeNull();
    expect(eur).not.toBeNull();
    expect(unknown).not.toBeNull();
    expect(screen.getAllByRole("table")).toHaveLength(3);

    // USD rows carry USD amounts only; the EUR amount never appears in the USD table.
    expect(within(usd!).getByText(formatCurrency(110000, "USD"))).toBeInTheDocument();
    expect(within(usd!).queryByText(formatCurrency(90000, "EUR"))).not.toBeInTheDocument();
    expect(within(eur!).getByText(formatCurrency(90000, "EUR"))).toBeInTheDocument();
    expect(within(eur!).queryByText(formatCurrency(110000, "USD"))).not.toBeInTheDocument();
  });

  it("shows a dash for a missing average and plain numbers when no currency is set", () => {
    render(<CompensationCard data={bundle({ compensationBySeniority: COMPENSATION })} rangeText="in all time" status={READY} />);

    const usd = screen.getByRole("heading", { name: "USD" }).closest("section");
    // The junior row has no maximum, so its max cell shows a dash.
    expect(within(usd!).getByText("—")).toBeInTheDocument();
    const unknown = screen.getByRole("heading", { name: "Currency not set" }).closest("section");
    expect(within(unknown!).getByText("50")).toBeInTheDocument();
  });

  it("renders an empty state when no compensation is in range", () => {
    render(<CompensationCard data={bundle({ compensationBySeniority: [] })} rangeText="in the last 7 days" status={READY} />);

    expect(screen.getByText("No compensation data in this range")).toBeInTheDocument();
  });
});

describe("DeclineReasonsCard", () => {
  it("shows the top eight reasons and groups the rest as Other", () => {
    const top = Array.from({ length: 8 }, (_, index) => ({ reason: `Reason ${index + 1}`, count: 10 - index }));
    render(
      <DeclineReasonsCard
        data={bundle({ declineReasons: top, declineOther: 3 })}
        rangeText="in the last 30 days"
        status={READY}
      />
    );

    const list = screen.getByRole("list", { name: "Decline reasons" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(9);
    const other = within(list).getByText("Other").closest("li");
    expect(other).toHaveTextContent("3");
  });

  it("does not add an Other row when there are no more reasons", () => {
    render(
      <DeclineReasonsCard
        data={bundle({ declineReasons: [{ reason: "Salary", count: 1 }], declineOther: 0 })}
        rangeText="in the last 30 days"
        status={READY}
      />
    );

    expect(screen.queryByText("Other")).not.toBeInTheDocument();
  });
});

describe("MatchScoreCard", () => {
  const ROWS: ScoreOutcomeRow[] = [
    {
      bucket: "7-8",
      evaluations: 3,
      withApplication: 2,
      offers: 1,
      declined: 0,
      open: 1,
      offerRate: { value: 0.5, n: 2 },
      avgScore: 7.5,
    },
  ];

  it("names the score as Match score and captions the range it covers", () => {
    render(<MatchScoreCard rows={ROWS} rangeText="in the last 30 days" status={READY} />);

    expect(screen.getByRole("heading", { name: "Match score" })).toBeInTheDocument();
    expect(screen.getByText(/Evaluations by match score, 0 to 10\. in the last 30 days\./)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /Match score distribution\. in the last 30 days\./ });
    expect(within(table).getByRole("cell", { name: "7 to 8" })).toBeInTheDocument();
  });

  it("renders an empty state with no evaluations", () => {
    render(<MatchScoreCard rows={[]} rangeText="in all time" status={READY} />);

    expect(screen.getByText("No evaluations in this range")).toBeInTheDocument();
  });
});

function bundle(overrides: Partial<InsightsBundle>): InsightsBundle {
  return {
    scoreOutcomes: [],
    outcomeBreakdown: [],
    declineReasons: [],
    declineOther: 0,
    compensationBySeniority: [],
    interviewOutcomes: [],
    ...overrides,
  };
}
