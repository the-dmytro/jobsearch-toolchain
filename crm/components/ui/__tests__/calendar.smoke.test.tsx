import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Calendar } from "@/components/ui/calendar";

describe("Calendar (react-day-picker v10)", () => {
  it("renders a month grid with day buttons and a caption", () => {
    render(
      <Calendar
        mode="range"
        defaultMonth={new Date(2026, 10, 1)}
        selected={{ from: new Date(2026, 10, 3), to: new Date(2026, 10, 7) }}
      />
    );

    expect(screen.getByRole("grid")).toBeInTheDocument();
    expect(screen.getAllByRole("gridcell").length).toBeGreaterThan(0);
    expect(screen.getByText("November 2026")).toBeInTheDocument();
  });
});
