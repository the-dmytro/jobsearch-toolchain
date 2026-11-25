import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DateRangePicker } from "@/components/crm/date-range-picker";
import { DateRangeProvider } from "@/lib/date-range-context";
import { useHydrated } from "@/lib/use-hydrated";

const PLACEHOLDER = "Choose dates";

describe("DateRangePicker label", () => {
  it("renders a stable placeholder on the server, with no date in the markup", () => {
    const html = renderToString(
      <DateRangeProvider>
        <DateRangePicker />
      </DateRangeProvider>
    );

    expect(html).toContain(PLACEHOLDER);
    expect(html).not.toMatch(/ – /);
  });

  it("shows the range once mounted in the browser", async () => {
    render(
      <DateRangeProvider>
        <DateRangePicker />
      </DateRangeProvider>
    );

    expect(await screen.findByText(/ – /)).toBeInTheDocument();
    expect(screen.queryByText(PLACEHOLDER)).toBeNull();
  });
});

describe("useHydrated", () => {
  it("is false on the server and true after mount", () => {
    function Probe() {
      return <span>{useHydrated() ? "mounted" : "server"}</span>;
    }
    expect(renderToString(<Probe />)).toContain("server");
    render(<Probe />);
    expect(screen.getByText("mounted")).toBeInTheDocument();
  });
});
