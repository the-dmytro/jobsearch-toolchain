import { AppSidebar } from "@/components/crm/app-sidebar";
import { CommandPalette } from "@/components/crm/command-palette";
import { DashboardShell } from "@/components/crm/dashboard-shell";
import { DateRangeProvider } from "@/lib/date-range-context";
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <DateRangeProvider>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md focus:ring-2 focus:ring-ring focus:outline-none"
        >
          Skip to content
        </a>
        <AppSidebar />
        {/* SidebarInset renders the page's <main> landmark; the skip link targets it. */}
        <SidebarInset
          id="main"
          tabIndex={-1}
          className="flex min-h-screen min-w-0 flex-col focus:outline-none"
        >
          <CommandPalette />
          <DashboardShell>{children}</DashboardShell>
        </SidebarInset>
      </DateRangeProvider>
    </SidebarProvider>
  );
}
