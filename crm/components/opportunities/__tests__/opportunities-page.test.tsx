import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OpportunitiesPage } from "@/components/opportunities/opportunities-page";

const client = vi.hoisted(() => ({ next: vi.fn() }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    from: () => ({
      select: () => ({
        order: () => ({
          range: (from: number, to: number) => client.next(from, to),
        }),
      }),
    }),
  }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <OpportunitiesPage />
    </QueryClientProvider>
  );
}

describe("OpportunitiesPage states", () => {
  it("shows a loading state while the first page is in flight", () => {
    client.next.mockReturnValue(new Promise(() => {}));
    renderPage();

    expect(screen.getByRole("status", { name: "Loading opportunities" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Opportunities" })).toBeInTheDocument();
  });

  it("shows an empty state with a next step when nothing has been found", async () => {
    client.next.mockResolvedValue({ data: [], error: null });
    renderPage();

    expect(await screen.findByText("No opportunities yet")).toBeInTheDocument();
    expect(screen.getByText(/appear here once a search run finds a posting/)).toBeInTheDocument();
  });

  it("shows a friendly error with retry, and never the raw database message", async () => {
    client.next.mockResolvedValue({
      data: null,
      error: { code: "XX000", message: "permission denied for table opportunities" },
    });
    renderPage();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Opportunities couldn't load");
    expect(alert).toHaveTextContent("You don't have permission to see this.");
    expect(alert.textContent).not.toContain("opportunities");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
