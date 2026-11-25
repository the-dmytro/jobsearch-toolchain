"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DateRangePicker } from "@/components/crm/date-range-picker";
import { ThemeToggle } from "@/components/crm/theme-toggle";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { isDemoMode } from "@/lib/demo";
import { routeUsesDateRange } from "@/lib/date-range-routes";
import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  applications: "Applications",
  opportunities: "Opportunities",
  companies: "Companies",
  contacts: "Contacts",
  interviews: "Interviews",
  communications: "Communications",
  transcripts: "Transcripts",
  runs: "Automation runs",
  insights: "Insights",
  settings: "Settings",
};

export function breadcrumbSegments(pathname: string) {
  if (pathname === "/") {
    return [{ href: "/", label: "Dashboard" }];
  }

  const parts = pathname.split("/").filter(Boolean);
  return parts.map((part, index) => {
    const href = `/${parts.slice(0, index + 1).join("/")}`;
    // A segment under a known section is a record id (a UUID): show "Details", not the id.
    const label = LABELS[part] ?? (index > 0 && LABELS[parts[0]] ? "Details" : part.replace(/-/g, " "));
    return { href, label };
  });
}

/**
 * Header and content wrapper for dashboard pages. It renders inside the shell's
 * <main id="main"> (see `app/(dashboard)/layout.tsx`), so it must not add another
 * <main>.
 *
 * On narrow screens (under 640px) the breadcrumb shows only the current page, and
 * the date range becomes a select. Nothing is hidden outright.
 */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const segments = breadcrumbSegments(pathname);
  const showDateRange = routeUsesDateRange(pathname);

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-2 border-b bg-background px-3 sm:px-4">
        <SidebarTrigger className="-ml-1 shrink-0" aria-label="Toggle navigation menu" />
        <Separator orientation="vertical" className="mr-1 h-6 shrink-0 sm:mr-2" />
        <Breadcrumb className="min-w-0 flex-1">
          <BreadcrumbList className="min-w-0 flex-nowrap">
            {segments.map((segment, index) => {
              const isLast = index === segments.length - 1;
              return (
                <span
                  key={segment.href}
                  className={isLast ? "contents min-w-0" : "contents max-sm:hidden"}
                >
                  <BreadcrumbItem className="min-w-0">
                    {isLast ? (
                      <BreadcrumbPage className="truncate capitalize">
                        {segment.label}
                      </BreadcrumbPage>
                    ) : (
                      <BreadcrumbLink
                        render={<Link href={segment.href} />}
                        className="capitalize"
                      >
                        {segment.label}
                      </BreadcrumbLink>
                    )}
                  </BreadcrumbItem>
                  {!isLast ? <BreadcrumbSeparator /> : null}
                </span>
              );
            })}
          </BreadcrumbList>
        </Breadcrumb>
        <div className="flex shrink-0 items-center gap-1">
          {isDemoMode() ? (
            <Badge variant="secondary" className="hidden lg:inline-flex">
              Demo mode
            </Badge>
          ) : null}
          {showDateRange ? <DateRangePicker /> : null}
          <ThemeToggle />
        </div>
      </header>
      {/* overflow-x-clip: a child that is wider than the page clips here instead of widening the document. relative: absolutely positioned descendants such as sr-only text are clipped here too. Wide tables and the stage board scroll in their own containers. */}
      <div className="relative flex min-w-0 flex-1 flex-col overflow-x-clip p-4 md:p-6">{children}</div>
    </>
  );
}
