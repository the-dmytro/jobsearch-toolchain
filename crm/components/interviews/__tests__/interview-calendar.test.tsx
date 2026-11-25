import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InterviewCalendar, countInterviewsByDay, dayKey } from "@/components/interviews/interview-calendar";

const november = new Date(2026, 10, 1);

describe("countInterviewsByDay", () => {
  it("counts interviews per local day and skips missing or invalid dates", () => {
    const counts = countInterviewsByDay([
      new Date(2026, 10, 12, 10, 0).toISOString(),
      new Date(2026, 10, 12, 15, 30).toISOString(),
      new Date(2026, 10, 20, 9, 0).toISOString(),
      null,
      "not a date",
    ]);
    expect(counts.get("2026-11-12")).toBe(2);
    expect(counts.get("2026-11-20")).toBe(1);
    expect(counts.size).toBe(2);
    expect(dayKey(new Date(2026, 10, 3))).toBe("2026-11-03");
  });
});

describe("InterviewCalendar labels", () => {
  it("gives a day with interviews an accessible count, not just a tint", () => {
    render(
      <InterviewCalendar
        scheduledAt={[
          new Date(2026, 10, 12, 10, 0).toISOString(),
          new Date(2026, 10, 12, 15, 0).toISOString(),
          new Date(2026, 10, 20, 9, 0).toISOString(),
        ]}
        month={november}
        onMonthChange={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "12 Nov 2026, 2 interviews" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20 Nov 2026, 1 interview" })).toBeInTheDocument();
    // Only the two booked days carry the interview label.
    expect(screen.getAllByRole("button", { name: /interview/ })).toHaveLength(2);
  });

  it("explains the dot in visible text", () => {
    render(<InterviewCalendar scheduledAt={[]} month={november} onMonthChange={vi.fn()} />);
    expect(screen.getByText("Days with an interview are marked with a dot.")).toBeInTheDocument();
  });

  it("keeps the dot decorative and out of the accessible name", () => {
    render(
      <InterviewCalendar
        scheduledAt={[new Date(2026, 10, 12, 10, 0).toISOString()]}
        month={november}
        onMonthChange={vi.fn()}
      />
    );
    const booked = screen.getByRole("button", { name: "12 Nov 2026, 1 interview" });
    expect(within(booked).getByText("12")).toBeInTheDocument();
    expect(booked.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });
});
