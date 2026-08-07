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
        <AppSidebar />
        <SidebarInset className="flex min-h-screen flex-col">
          <CommandPalette />
          <DashboardShell>{children}</DashboardShell>
        </SidebarInset>
      </DateRangeProvider>
    </SidebarProvider>
  );
}
